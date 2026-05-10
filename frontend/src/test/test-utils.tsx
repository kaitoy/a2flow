import { configureStore, type Reducer, type UnknownAction } from "@reduxjs/toolkit";
import { type RenderOptions, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { Provider } from "react-redux";
import { ThemeProvider } from "@/components/ThemeProvider";
import type { RootState } from "@/store";
import chatReducer from "@/store/chatSlice";

export function makeStore(preloadedState?: Partial<RootState>) {
  return configureStore({
    reducer: {
      chat: chatReducer as Reducer<RootState["chat"], UnknownAction, RootState["chat"] | undefined>,
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
