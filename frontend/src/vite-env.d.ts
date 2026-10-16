/// <reference types="vite/client" />
/// <reference types="@testing-library/jest-dom" />
/// <reference types="vitest/globals" />

declare module "*.css" {
  const content: Record<string, string>;
  export default content;
}
