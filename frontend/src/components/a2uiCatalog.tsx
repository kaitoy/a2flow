import type { ReactComponentImplementation } from "@a2ui/react/v0_9";
import { basicCatalog } from "@a2ui/react/v0_9";
import { Catalog } from "@a2ui/web_core/v0_9";
import { BASIC_FUNCTIONS } from "@a2ui/web_core/v0_9/basic_catalog";
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

export const tailwindCatalog = new Catalog<ReactComponentImplementation>(
  "https://a2ui.org/specification/v0_9/basic_catalog.json",
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
