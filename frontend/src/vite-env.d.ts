/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EDGEML_API_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
