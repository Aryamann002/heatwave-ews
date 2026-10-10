/// <reference types="vite/client" />
interface Window {
  HeatSafeUI?: { navigate: (url: string, replace?: boolean) => void };
}
