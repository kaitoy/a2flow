/**
 * A2UI catalog that overrides the standard basic catalog components with custom
 * Tailwind-styled implementations, keeping any unoverridden components from the base catalog.
 * Since `@a2ui/react` 0.13 the base catalog lives in `@a2ui/web_core` and renders those
 * remaining components as custom elements.
 */
import type { ReactCatalogComponent } from "@a2ui/react/v0_9";
import { Catalog } from "@a2ui/web_core/v0_9";
import { BASIC_FUNCTIONS, basicCatalog } from "@a2ui/web_core/v0_9/basic_catalog";
import { A2UI_CATALOG_ID } from "@/lib/a2uiCatalogId";
import { customButton } from "./a2ui/button";
import { customCard } from "./a2ui/card";
import { customChoicePicker } from "./a2ui/choicePicker";
import { customColumn } from "./a2ui/column";
import { customRow } from "./a2ui/row";
import { customText } from "./a2ui/text";
import { customTextField } from "./a2ui/textField";

const OVERRIDDEN = new Set([
  "Text",
  "Button",
  "Card",
  "Row",
  "Column",
  "TextField",
  "ChoicePicker",
]);

const remainingComponents = Array.from(basicCatalog.components.values()).filter(
  (c) => !OVERRIDDEN.has(c.name)
);

export const tailwindCatalog = new Catalog<ReactCatalogComponent>(
  A2UI_CATALOG_ID,
  basicCatalog.protocolVersion,
  [
    customText,
    customButton,
    customCard,
    customRow,
    customColumn,
    customTextField,
    customChoicePicker,
    ...remainingComponents,
  ],
  BASIC_FUNCTIONS
);
