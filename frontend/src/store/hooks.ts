import { useDispatch, useSelector } from "react-redux";
import type { AppDispatch, RootState } from "./index";

/** Typed wrapper around Redux's ``useDispatch`` that infers the full ``AppDispatch`` type. */
export const useAppDispatch = () => useDispatch<AppDispatch>();

/** Typed wrapper around Redux's ``useSelector`` that constrains the state type to ``RootState``. */
export const useAppSelector = <T>(selector: (state: RootState) => T): T => useSelector(selector);
