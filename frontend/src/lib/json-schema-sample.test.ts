import { describe, expect, it } from "vitest";
import { sampleFromJsonSchema, sampleObjectTextFromJsonSchema } from "./json-schema-sample";

describe("sampleFromJsonSchema", () => {
  it("fills every declared property, required or not", () => {
    expect(
      sampleFromJsonSchema({
        type: "object",
        required: ["id"],
        properties: {
          id: { type: "string" },
          count: { type: "integer" },
          ok: { type: "boolean" },
        },
      })
    ).toEqual({ id: "", count: 0, ok: false });
  });

  it("gives an array one element so the item shape is visible", () => {
    expect(
      sampleFromJsonSchema({
        type: "object",
        properties: {
          issues: {
            type: "array",
            items: { type: "object", properties: { key: { type: "string" } } },
          },
        },
      })
    ).toEqual({ issues: [{ key: "" }] });
  });

  it("leaves an array with no item schema empty", () => {
    expect(sampleFromJsonSchema({ type: "array" })).toEqual([]);
  });

  it("prefers a default over the type's placeholder", () => {
    expect(
      sampleFromJsonSchema({
        type: "object",
        properties: { status: { type: "string", default: "approved" } },
      })
    ).toEqual({ status: "approved" });
  });

  it("uses a const, and the first enum value", () => {
    expect(sampleFromJsonSchema({ const: 42 })).toBe(42);
    expect(sampleFromJsonSchema({ enum: ["pending", "approved"] })).toBe("pending");
  });

  it("takes the non-null half of a nullable type union", () => {
    expect(sampleFromJsonSchema({ type: ["string", "null"] })).toBe("");
  });

  it("takes the first branch of a combinator", () => {
    expect(
      sampleFromJsonSchema({
        oneOf: [{ type: "object", properties: { ok: { type: "boolean" } } }, { type: "string" }],
      })
    ).toEqual({ ok: false });
  });

  it("treats a bare properties bag as an object", () => {
    expect(sampleFromJsonSchema({ properties: { a: { type: "string" } } })).toEqual({ a: "" });
  });

  it("follows a $ref into the same document", () => {
    expect(
      sampleFromJsonSchema({
        type: "object",
        $defs: {
          Issue: { type: "object", properties: { key: { type: "string" } } },
        },
        properties: {
          issues: { type: "array", items: { $ref: "#/$defs/Issue" } },
          total: { type: "integer" },
        },
      })
    ).toEqual({ issues: [{ key: "" }], total: 0 });
  });

  it("yields null for a $ref it cannot resolve, and for a non-schema", () => {
    expect(sampleFromJsonSchema({ $ref: "#/$defs/Node" })).toBeNull();
    expect(sampleFromJsonSchema({ $ref: "https://example.com/other.json#/A" })).toBeNull();
    expect(sampleFromJsonSchema("not a schema")).toBeNull();
    expect(sampleFromJsonSchema(null)).toBeNull();
  });

  it("stops rather than hanging on a $ref that points back at itself", () => {
    const sample = sampleFromJsonSchema({
      $defs: { Node: { type: "object", properties: { child: { $ref: "#/$defs/Node" } } } },
      $ref: "#/$defs/Node",
    });
    expect(sample).toBeTypeOf("object");
    expect(JSON.stringify(sample)).toContain('"child"');
  });

  it("stops rather than hanging on a schema that nests without end", () => {
    type Nested = { type: string; properties: { child: Nested | { type: string } } };
    const leaf = { type: "string" };
    let schema: Nested = { type: "object", properties: { child: leaf } };
    for (let i = 0; i < 50; i += 1) {
      schema = { type: "object", properties: { child: schema } };
    }
    const sample = sampleFromJsonSchema(schema) as Record<string, unknown>;
    // One object per level from 0 through MAX_DEPTH, then the walk gives up.
    let node: unknown = sample;
    for (let i = 0; i <= 8; i += 1) {
      expect(node).toBeTypeOf("object");
      node = (node as Record<string, unknown>).child;
    }
    expect(node).toBeNull();
  });
});

describe("sampleObjectTextFromJsonSchema", () => {
  it("returns pretty-printed JSON", () => {
    expect(
      sampleObjectTextFromJsonSchema({
        type: "object",
        properties: { total: { type: "integer" } },
      })
    ).toBe('{\n  "total": 0\n}');
  });

  it("falls back to an empty object when the schema is not object-shaped", () => {
    expect(sampleObjectTextFromJsonSchema({ type: "string" })).toBe("{}");
    expect(sampleObjectTextFromJsonSchema(undefined)).toBe("{}");
  });
});
