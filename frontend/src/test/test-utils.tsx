import { configureStore, type Reducer, type UnknownAction } from "@reduxjs/toolkit";
import { type RenderOptions, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { Provider } from "react-redux";
import { ThemeProvider } from "@/components/ThemeProvider";
import type { RootState } from "@/store";
import authReducer from "@/store/authSlice";
import chatReducer from "@/store/chatSlice";
import notificationsReducer from "@/store/notificationsSlice";

export function makeStore(preloadedState?: Partial<RootState>) {
  return configureStore({
    reducer: {
      chat: chatReducer as Reducer<RootState["chat"], UnknownAction, RootState["chat"] | undefined>,
      auth: authReducer as Reducer<RootState["auth"], UnknownAction, RootState["auth"] | undefined>,
      notifications: notificationsReducer as Reducer<
        RootState["notifications"],
        UnknownAction,
        RootState["notifications"] | undefined
      >,
    },
    preloadedState,
  });
}

type AppStore = ReturnType<typeof makeStore>;

interface ExtendedRenderOptions extends Omit<RenderOptions, "wrapper"> {
  preloadedState?: Partial<RootState>;
  store?: AppStore;
}

function renderWithStore(
  ui: ReactElement,
  { preloadedState, store, ...renderOptions }: ExtendedRenderOptions = {}
) {
  const testStore = store ?? makeStore(preloadedState);
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <ThemeProvider>
        <Provider store={testStore}>{children}</Provider>
      </ThemeProvider>
    );
  }
  return { store: testStore, ...render(ui, { wrapper: Wrapper, ...renderOptions }) };
}

export * from "@testing-library/react";
export { renderWithStore as render };
