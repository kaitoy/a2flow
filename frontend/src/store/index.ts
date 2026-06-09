/** Redux store configuration combining the chat, auth, and notifications slices. */
import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import chatReducer from "./chatSlice";
import notificationsReducer from "./notificationsSlice";

export const store = configureStore({
  reducer: {
    chat: chatReducer,
    auth: authReducer,
    notifications: notificationsReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
