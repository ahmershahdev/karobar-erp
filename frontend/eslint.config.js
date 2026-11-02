import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'src/lib/api/schema.d.ts'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
      '@typescript-eslint/no-confusing-void-expression': ['error', { ignoreArrowShorthand: true }],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-script-url': 'error',
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'Render text, not HTML. See docs/security.md.',
        },
        {
          selector: 'AssignmentExpression[left.property.name=/^(innerHTML|outerHTML)$/]',
          message: 'Use textContent. See docs/security.md.',
        },
        {
          selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
          message: 'Use DOM APIs. See docs/security.md.',
        },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'localStorage',
          property: 'setItem',
          message: 'No tokens or business data in localStorage.',
        },
        {
          object: 'import',
          property: 'meta',
          message: 'Read configuration through src/lib/env.ts.',
        },
      ],
    },
  },
  {
    files: ['src/lib/env.ts', 'vite.config.ts'],
    rules: { 'no-restricted-properties': 'off' },
  },
  {
    files: ['**/*.test.ts', 'src/test/**'],
    rules: { '@typescript-eslint/no-non-null-assertion': 'off' },
  },
);
