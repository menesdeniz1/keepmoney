// ESLint düz yapılandırma (flat config, ESLint 9).
//
// Arayüzde HİÇ lint yoktu: `package.json`da bir `lint` betiği duruyordu ama
// ne yapılandırma dosyası ne de eslint bağımlılığı vardı — çalıştırıldığında
// hata veriyordu ve CI onu hiç çağırmıyordu. Backend'de `ruff check` CI'da
// koşarken arayüzün denetimsiz kalması tutarsızdı.
//
// Kurallar dar tutuldu: tip kontrolünü `tsc` zaten yapıyor. Buradaki değer,
// tip sisteminin YAKALAYAMADIĞI hatalarda:
//   • react-hooks — bağımlılık dizisi hataları (bayat closure, sonsuz döngü)
//   • no-floating-promises — beklenmeyen async hata yutulması
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'coverage'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Kullanılmayan değişken: `_` önekli olanlar bilinçli atılmış sayılır.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // Testlerde vitest global'leri (`describe`, `it`, `expect`) kullanılıyor.
    files: ['**/*.test.ts', '**/*.test.tsx'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
    rules: { '@typescript-eslint/no-non-null-assertion': 'off' },
  },
)
