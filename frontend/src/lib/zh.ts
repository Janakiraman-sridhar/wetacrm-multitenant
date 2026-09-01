import { z } from "zod";

/** zod helpers for form fields: HTML inputs give "" / NaN, the API wants null. */

export const optStr = z.preprocess((v) => (v === "" || v === undefined ? null : v), z.string().nullable());

export const reqStr = (message = "Required") => z.string().min(1, message);

export const optNum = z.preprocess(
  (v) => (v === "" || v === undefined || v === null || Number.isNaN(v) ? null : Number(v)),
  z.number().nullable()
);

export const numDefault = (def = 0) =>
  z.preprocess((v) => (v === "" || v === undefined || v === null || Number.isNaN(v) ? def : Number(v)), z.number());

export const optEmail = z.preprocess(
  (v) => (v === "" || v === undefined ? null : v),
  z.string().email("Invalid email").nullable()
);
