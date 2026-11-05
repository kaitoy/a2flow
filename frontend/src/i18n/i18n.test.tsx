import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiClientError, getApiErrorMessage } from "@/lib/api";
import { isLocale, LOCALES, matchLocale, parseAcceptLanguage } from "./config";
import { loadMessages } from "./load";
import { en, type Message, type MessageKey } from "./messages/en";
import { I18nProvider, useSetLocale, useT } from "./provider";
import { createTranslator, defaultTranslator, setActiveTranslator } from "./translate";

afterEach(() => setActiveTranslator(defaultTranslator));

describe("matchLocale", () => {
  it.each([
    [["ja-JP", "en"], "ja"],
    [["de", "fr-CA"], "fr"],
    [["zh-CN"], "zh-CN"],
    [["zh"], "zh-CN"],
    [["zh-Hans-SG"], "zh-CN"],
    [["ko-KR"], "ko"],
    [["es-419"], "es"],
    [["de"], "en"],
    [["not a tag!"], "en"],
    [[], "en"],
  ])("maps %j to %s", (tags, expected) => {
    expect(matchLocale(tags)).toBe(expected);
  });

  it.each(["zh-TW", "zh-HK", "zh-Hant"])("does not hand %s Simplified Chinese", (tag) => {
    expect(matchLocale([tag])).toBe("en");
    expect(matchLocale([tag, "ja"])).toBe("ja");
  });
});

describe("parseAcceptLanguage", () => {
  it("orders by quality and drops wildcards and refusals", () => {
    expect(parseAcceptLanguage("fr;q=0.5, ja, de;q=0, *;q=0.1, ko;q=0.8")).toEqual([
      "ja",
      "ko",
      "fr",
    ]);
  });

  it("treats a missing header as no preference", () => {
    expect(parseAcceptLanguage(null)).toEqual([]);
  });
});

describe("isLocale", () => {
  it("rejects values that are not supported languages, including inherited keys", () => {
    expect(isLocale("ja")).toBe(true);
    expect(isLocale("de")).toBe(false);
    expect(isLocale("constructor")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});

describe("createTranslator", () => {
  const catalog = {
    ...en,
    "time.justNow": "now {name} {missing}",
    "time.minutesAgo": { one: "one form", other: "other form" },
  };

  it("fills placeholders and leaves unknown ones visible", () => {
    const t = createTranslator("en", catalog);
    expect(t("time.justNow", { name: "x" })).toBe("now x {missing}");
  });

  it("picks the plural form the language calls for", () => {
    expect(createTranslator("en", catalog)("time.minutesAgo", { count: 0 })).toBe("other form");
    expect(createTranslator("fr", catalog)("time.minutesAgo", { count: 0 })).toBe("one form");
    expect(createTranslator("ko", catalog)("time.minutesAgo", { count: 1 })).toBe("other form");
  });

  it("falls back to English for a key the catalog lacks", () => {
    const { "time.daysAgo": _dropped, ...partial } = en;
    const t = createTranslator("ja", partial as typeof en);
    expect(t("time.daysAgo", { count: 3 })).toBe("3d ago");
  });

  it("maybe passes text through unless it is a key", () => {
    const t = createTranslator("en", en);
    expect(t.maybe("Already finished text")).toBe("Already finished text");
    expect(t.maybe("time.justNow")).toBe("just now");
  });

  it("rich embeds React nodes in the message", () => {
    const t = createTranslator("en", catalog);
    render(<p>{t.rich("time.justNow", { name: <b>bold</b>, missing: "m" })}</p>);
    expect(screen.getByText("bold").tagName).toBe("B");
    expect(screen.getByText(/^now/)).toHaveTextContent("now bold m");
  });
});

describe("catalogs", () => {
  /** Every text variant of a message, so plural forms are checked too. */
  function texts(message: Message): string[] {
    return typeof message === "string" ? [message] : Object.values(message);
  }

  function placeholders(text: string): string[] {
    return [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
  }

  it.each(LOCALES)("%s uses the same placeholders as English", async (locale) => {
    const catalog = await loadMessages(locale);
    const wrong: string[] = [];
    for (const key of Object.keys(en) as MessageKey[]) {
      const expected = new Set(texts(en[key]).flatMap(placeholders));
      const actual = new Set(texts(catalog[key]).flatMap(placeholders));
      // A language without plural forms may legitimately drop `count`.
      expected.delete("count");
      actual.delete("count");
      if ([...expected].sort().join() !== [...actual].sort().join()) wrong.push(key);
    }
    expect(wrong).toEqual([]);
  });

  it.each(LOCALES)(
    "%s gives a plural message an `other` form and keeps no empty text",
    async (locale) => {
      const catalog = await loadMessages(locale);
      for (const key of Object.keys(en) as MessageKey[]) {
        const message = catalog[key];
        if (typeof message !== "string") expect(message.other, key).toBeTruthy();
        for (const text of texts(message)) expect(text.trim(), key).not.toBe("");
      }
    }
  );
});

describe("I18nProvider", () => {
  function Probe() {
    const t = useT();
    const setLocale = useSetLocale();
    return (
      <button type="button" onClick={() => void setLocale("ja")}>
        {t("time.justNow")}
      </button>
    );
  }

  it("works as English without a provider", () => {
    render(<Probe />);
    expect(screen.getByRole("button", { name: "just now" })).toBeInTheDocument();
  });

  it("renders the language the server resolved", async () => {
    render(
      <I18nProvider locale="ja" messages={await loadMessages("ja")}>
        <Probe />
      </I18nProvider>
    );
    expect(screen.getByRole("button", { name: "たった今" })).toBeInTheDocument();
  });

  it("switches language in place and updates the document language", async () => {
    render(
      <I18nProvider locale="en">
        <Probe />
      </I18nProvider>
    );
    await act(async () => screen.getByRole("button").click());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "たった今" })).toBeInTheDocument()
    );
    expect(document.documentElement.lang).toBe("ja");
  });
});

describe("getApiErrorMessage", () => {
  const notFound = new ApiClientError("NOT_FOUND", "User abc not found");

  it("keeps the backend's message in English", () => {
    expect(getApiErrorMessage(notFound)).toBe("User abc not found");
  });

  describe("in another language", () => {
    async function useJapanese() {
      setActiveTranslator(createTranslator("ja", await loadMessages("ja")));
    }

    it("translates by error code", async () => {
      await useJapanese();
      expect(getApiErrorMessage(notFound)).toBe("対象が見つかりません。");
    });

    it("keeps the backend's reason after the translation", async () => {
      await useJapanese();
      const error = new ApiClientError("INVALID_SECRET", "x", { reason: "missing key" });
      expect(getApiErrorMessage(error)).toBe(
        "シークレットの設定が正しくありません。 (missing key)"
      );
    });

    it("translates a bare HTTP failure with its status", async () => {
      await useJapanese();
      const error = new ApiClientError("HTTP_503", "x", undefined, undefined, 503);
      expect(getApiErrorMessage(error)).toContain("503");
      expect(getApiErrorMessage(error)).not.toBe("x");
    });

    it("falls back to the backend's message for an unknown code", async () => {
      await useJapanese();
      expect(getApiErrorMessage(new ApiClientError("BRAND_NEW", "raw message"))).toBe(
        "raw message"
      );
    });
  });

  it("translates the fallback for something that is not an Error", async () => {
    setActiveTranslator(createTranslator("fr", await loadMessages("fr")));
    expect(getApiErrorMessage("boom")).toBe("Une erreur est survenue. Veuillez réessayer.");
  });
});
