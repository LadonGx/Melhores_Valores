# apps/web/src/components/ — Reusable UI Primitives

## Objective
Generic, domain-agnostic UI components used across multiple pages and features.

## Components

| Component | Purpose |
|---|---|
| `Button/` | Styled button with variants (primary, secondary, danger) |
| `Card/` | Container with shadow/border styling |
| `Header/` | Top navigation bar |
| `Input/` | Styled text input with label/error |
| `Modal/` | Overlay dialog with close button |
| `Sidebar/` | Left navigation menu with route links |
| `Table/` | Data table with sortable columns |
| `Toast/` | Notification messages (success, error, info) |

## Rules

- **Components are domain-agnostic.** If a component is tied to products or search, it belongs in `features/`, not here.
- **No business logic.** Components receive props and render UI.
- **No server state.** Components do not call hooks or services.
- **CSS Modules only.** One `.module.css` per component.
- **Named exports.** `export function Button(...)`, not default.

## Component Pattern

```tsx
// components/Button/index.tsx
import styles from './Button.module.css'

interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'danger'
  onClick?: () => void
  disabled?: boolean
  children: React.ReactNode
}

export function Button({ variant = 'primary', ...props }: ButtonProps) {
  return (
    <button className={`${styles.button} ${styles[variant]}`} {...props} />
  )
}
```

## What NOT to Do

- Do not add data fetching to components.
- Do not import from `features/` or `services/` — components only receive props.
- Do not create feature-specific variants here — extend in feature components.

## Adding a New Component

1. Create `components/<Name>/index.tsx` and `components/<Name>/<Name>.module.css`
2. Export from `components/<Name>/index.tsx`
3. Import in consuming component: `import { Name } from '@/components/Name'`

## Risks

- Changes to component props break all usages — check before modifying interfaces.
- Styling changes affect all pages using the component — test across routes.
