/**
 * Cyclone Twin — Centralized i18n & Localization Infrastructure Layer
 * React Context, Locale Switcher Hooks, and Intl Formatters.
 */

import React, { createContext, useContext, useState, useCallback, useMemo } from "react";
import { en } from "./locales/en.js";
import { ta } from "./locales/ta.js";

const dictionaries = {
  en,
  ta,
};

export const SUPPORTED_LOCALES = [
  { code: "en", label: "English", nativeName: "English" },
  { code: "ta", label: "Tamil", nativeName: "தமிழ்" },
];

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [locale, setLocaleState] = useState(() => {
    try {
      const saved = localStorage.getItem("cyclone_twin_locale");
      if (saved && dictionaries[saved]) {
        return saved;
      }
    } catch {
      // LocalStorage access fallback
    }
    return "en";
  });

  const setLocale = useCallback((newLocale) => {
    if (dictionaries[newLocale]) {
      setLocaleState(newLocale);
      try {
        localStorage.setItem("cyclone_twin_locale", newLocale);
      } catch {
        // ignore
      }
    }
  }, []);

  /**
   * Translate a dot-notated key string (e.g., 'header.title', 'reportTypes.ROAD_FLOODED')
   */
  const t = useCallback(
    (keyPath, params = {}) => {
      if (!keyPath || typeof keyPath !== "string") return "";

      const keys = keyPath.split(".");
      let val = dictionaries[locale];

      // Navigate dictionary
      for (const k of keys) {
        if (val && typeof val === "object" && k in val) {
          val = val[k];
        } else {
          val = null;
          break;
        }
      }

      // Fallback to English dictionary if key missing in target locale
      if (val === null || val === undefined) {
        let fallbackVal = dictionaries["en"];
        for (const k of keys) {
          if (fallbackVal && typeof fallbackVal === "object" && k in fallbackVal) {
            fallbackVal = fallbackVal[k];
          } else {
            fallbackVal = null;
            break;
          }
        }
        val = fallbackVal;
      }

      if (val === null || val === undefined) {
        return keyPath; // Return key as ultimate fallback
      }

      if (typeof val !== "string") {
        return String(val);
      }

      // Parameter interpolation `{param}`
      return val.replace(/\{(\w+)\}/g, (_, p) => (p in params ? params[p] : `{${p}}`));
    },
    [locale]
  );

  /**
   * Locale-aware Number Formatter
   */
  const formatNumber = useCallback(
    (value, options = {}) => {
      if (typeof value !== "number" || isNaN(value)) return "0";
      try {
        const intlLocale = locale === "ta" ? "ta-IN" : "en-US";
        return new Intl.NumberFormat(intlLocale, options).format(value);
      } catch {
        return String(value);
      }
    },
    [locale]
  );

  /**
   * Locale-aware Percentage Formatter
   */
  const formatPercent = useCallback(
    (value, decimals = 0) => {
      if (typeof value !== "number" || isNaN(value)) return "0%";
      try {
        const intlLocale = locale === "ta" ? "ta-IN" : "en-US";
        return new Intl.NumberFormat(intlLocale, {
          style: "percent",
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }).format(value);
      } catch {
        return `${(value * 100).toFixed(decimals)}%`;
      }
    },
    [locale]
  );

  /**
   * Locale-aware Date Formatter
   */
  const formatDate = useCallback(
    (dateInput, options = { month: "short", day: "numeric", year: "numeric" }) => {
      if (!dateInput) return "";
      try {
        const dateObj = dateInput instanceof Date ? dateInput : new Date(dateInput);
        const intlLocale = locale === "ta" ? "ta-IN" : "en-US";
        return new Intl.DateTimeFormat(intlLocale, options).format(dateObj);
      } catch {
        return String(dateInput);
      }
    },
    [locale]
  );

  /**
   * Locale-aware Time Formatter
   */
  const formatTime = useCallback(
    (dateInput, options = { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) => {
      if (!dateInput) return "";
      try {
        const dateObj = dateInput instanceof Date ? dateInput : new Date(dateInput);
        const intlLocale = locale === "ta" ? "ta-IN" : "en-US";
        return new Intl.DateTimeFormat(intlLocale, options).format(dateObj);
      } catch {
        return String(dateInput);
      }
    },
    [locale]
  );

  /**
   * Machine-Readable Report Type to Human Label Translator
   */
  const getReportTypeLabel = useCallback(
    (typeCode) => {
      if (!typeCode) return "";
      const translated = t(`reportTypes.${typeCode}`);
      return translated !== `reportTypes.${typeCode}` ? translated : typeCode;
    },
    [t]
  );

  /**
   * Machine-Readable Status to Human Label Translator
   */
  const getStatusLabel = useCallback(
    (statusCode) => {
      if (!statusCode) return "";
      const translated = t(`statuses.${statusCode}`);
      return translated !== `statuses.${statusCode}` ? translated : statusCode;
    },
    [t]
  );

  const contextValue = useMemo(
    () => ({
      locale,
      setLocale,
      supportedLocales: SUPPORTED_LOCALES,
      t,
      formatNumber,
      formatPercent,
      formatDate,
      formatTime,
      getReportTypeLabel,
      getStatusLabel,
    }),
    [locale, setLocale, t, formatNumber, formatPercent, formatDate, formatTime, getReportTypeLabel, getStatusLabel]
  );

  return <I18nContext.Provider value={contextValue}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
