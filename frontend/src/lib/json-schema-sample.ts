/**
 * @module json-schema-sample — Turn a JSON Schema into a filled-in skeleton.
 *
 * The tool-mock form asks an operator to type a JSON object that stands in for
 * what a tool returns. Given the tool's declared output schema, the keys are
 * already known, so the form offers the skeleton and lets the operator fill in
 * the values instead of transcribing the shape by hand.
 *
 * This is deliberately a *skeleton*, not a validator and not a faithful
 * instance: unconstrained strings come out empty and a union takes its first
 * branch. What the backend accepts is unchanged; a mocked response is still
 * only required to be a JSON object.
 *
 * A `$ref` pointing inside the same document is followed — an MCP server whose
 * tools return typed models advertises nested types as `$defs` entries, which
 * is most of them — while one pointing at another document becomes `null`.
 */

/**
 * How deep the walk goes before giving up.
 *
 * A schema may be recursive — a `$ref` back to an ancestor, or `properties`
 * nesting literally without end. The cap is what makes the walk total rather
 * than a hang. Each `$ref` hop spends a level, so it is set high enough that a
 * typed model's `$defs` indirection does not eat the budget by itself.
 */
const MAX_DEPTH = 8;

/** How many values the whole skeleton may contain, to bound a wide schema. */
const MAX_NODES = 500;

/** A schema object, as far as this module cares. */
type SchemaLike = Record<string, unknown>;

/** Mutable budget threaded through the walk. */
interface Budget {
  /** Values produced so far; the walk stops adding once it hits MAX_NODES. */
  count: number;
}

/**
 * Whether a value is a plain JSON object (and so possibly a schema).
 *
 * @param value - The value to test.
 * @returns True for a non-null, non-array object.
 */
function isSchemaLike(value: unknown): value is SchemaLike {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Pick the declared type, tolerating the `type: [...]` union form.
 *
 * @param schema - The schema to read.
 * @returns The chosen type name, or `undefined` when none is declared.
 */
function declaredType(schema: SchemaLike): string | undefined {
  const type = schema.type;
  if (typeof type === "string") return type;
  if (Array.isArray(type)) {
    // A nullable field is usually written `["string", "null"]`; the useful half
    // is the one that is not `null`.
    const first = type.find((entry) => typeof entry === "string" && entry !== "null");
    if (typeof first === "string") return first;
    if (type.length > 0) return "null";
  }
  return undefined;
}

/**
 * The first branch of a `allOf` / `anyOf` / `oneOf` combinator, if any.
 *
 * @param schema - The schema to read.
 * @returns The first branch that is itself a schema object, or `undefined`.
 */
function firstBranch(schema: SchemaLike): SchemaLike | undefined {
  for (const key of ["allOf", "anyOf", "oneOf"]) {
    const branches = schema[key];
    if (Array.isArray(branches)) {
      const branch = branches.find(isSchemaLike);
      if (branch !== undefined) return branch;
    }
  }
  return undefined;
}

/**
 * Follow a JSON Pointer into the schema document.
 *
 * Only same-document references (`#/$defs/Issue`) resolve; a pointer into
 * another document would need that document fetched, which this module does
 * not do.
 *
 * @param ref - The `$ref` value to resolve.
 * @param root - The document the reference is relative to.
 * @returns The referenced node, or `undefined` when it cannot be reached.
 */
function resolveRef(ref: string, root: SchemaLike): unknown {
  if (!ref.startsWith("#/")) return undefined;
  let node: unknown = root;
  for (const rawSegment of ref.slice(2).split("/")) {
    if (!isSchemaLike(node)) return undefined;
    // ~1 and ~0 are the pointer escapes for "/" and "~".
    const segment = decodeURIComponent(rawSegment).replace(/~1/g, "/").replace(/~0/g, "~");
    node = node[segment];
  }
  return node;
}

/**
 * Build the skeleton for one schema node.
 *
 * @param schema - The node to walk.
 * @param depth - How deep this node sits; the walk stops at {@link MAX_DEPTH}.
 * @param budget - Shared node budget, mutated as values are produced.
 * @param root - The whole schema document, for resolving `$ref`.
 * @returns The skeleton value for this node.
 */
function walk(schema: unknown, depth: number, budget: Budget, root: SchemaLike): unknown {
  if (!isSchemaLike(schema) || depth > MAX_DEPTH || budget.count >= MAX_NODES) return null;
  budget.count += 1;

  if (typeof schema.$ref === "string") {
    const target = resolveRef(schema.$ref, root);
    // Counting the reference itself against the depth is what stops a model
    // that contains itself from walking forever.
    return target === undefined ? null : walk(target, depth + 1, budget, root);
  }

  // An author-supplied example beats anything derived from the type.
  if ("default" in schema) return schema.default;
  if ("const" in schema) return schema.const;
  if (Array.isArray(schema.enum) && schema.enum.length > 0) return schema.enum[0];

  const type = declaredType(schema);

  if (type === "object" || (type === undefined && isSchemaLike(schema.properties))) {
    const properties = isSchemaLike(schema.properties) ? schema.properties : {};
    const sample: Record<string, unknown> = {};
    // Every declared property, not just the required ones: an optional field is
    // exactly the one an operator is most likely to forget the name of.
    for (const [key, child] of Object.entries(properties)) {
      if (budget.count >= MAX_NODES) break;
      sample[key] = walk(child, depth + 1, budget, root);
    }
    return sample;
  }

  if (type === "array") {
    // One element, so the operator sees the item shape and can copy it.
    if (!isSchemaLike(schema.items)) return [];
    return [walk(schema.items, depth + 1, budget, root)];
  }

  switch (type) {
    case "string":
      return "";
    case "number":
    case "integer":
      return 0;
    case "boolean":
      return false;
    case "null":
      return null;
    default:
      break;
  }

  const branch = firstBranch(schema);
  if (branch !== undefined) return walk(branch, depth + 1, budget, root);

  // No type, no properties, no combinator — a bare `{}`, or something this
  // module does not model.
  return null;
}

/**
 * Build a skeleton value matching a JSON Schema.
 *
 * @param schema - The schema to derive a skeleton from.
 * @returns A value shaped like the schema, with placeholder leaves.
 */
export function sampleFromJsonSchema(schema: unknown): unknown {
  const root = isSchemaLike(schema) ? schema : {};
  return walk(schema, 0, { count: 0 }, root);
}

/**
 * Build a skeleton **object** matching a JSON Schema, for a field that must
 * hold one.
 *
 * A mocked `structured` response is required to be a JSON object, so a schema
 * describing anything else — or nothing recognizable — yields an empty object
 * rather than a value the form would immediately reject.
 *
 * @param schema - The schema to derive a skeleton from.
 * @returns The skeleton as pretty-printed JSON text.
 */
export function sampleObjectTextFromJsonSchema(schema: unknown): string {
  const sample = sampleFromJsonSchema(schema);
  const object = isSchemaLike(sample) ? sample : {};
  return JSON.stringify(object, null, 2);
}
