import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
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
      // Downgraded to a warning after checking what it actually reports here.
      // Every tab loads its data by calling an async fetch function from a
      // mount effect, and the rule fires on the call itself -- not on a
      // synchronous setState. Verified two ways: TranslationContext touches
      // state only after "await fetch(...)" and is still reported, and
      // removing the one genuinely synchronous setState from BuildsTab's
      // fetch left the error exactly where it was. So the analyser treats any
      // setState reachable from the callee as if it ran during the effect,
      // and the only way to silence it is to restructure how five components
      // load their data -- a real UI change with real regression risk, for a
      // pattern that is not actually cascading renders. Kept visible as a
      // warning rather than hidden, and worth revisiting when the rule can
      // see await boundaries.
      'react-hooks/set-state-in-effect': 'warn',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off'
    },
  },
)
