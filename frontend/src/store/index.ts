import { configureStore } from "@reduxjs/toolkit";
import { setApiUserId } from "@/lib/api";
import chatReducer from "./chatSlice";

export const store = configureStore({
  reducer: {
    chat: chatReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

setApiUserId(store.getState().chat.userId);
store.subscribe(() => {
  setApiUserId(store.getState().chat.userId);
});
