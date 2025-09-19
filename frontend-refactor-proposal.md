# 🔧 Frontend Refactoring Proposal

## 1. Current State & Problem Definition

### Overall
- The frontend is built with **Next.js + TypeScript + Tailwind + shadcn/ui**, which is a strong modern stack.  
- There are **good practices in place**: reusable UI components, hook-based state management (`useJobs`, `useConfig`, `useSession`), and type safety with TypeScript.  

### Strengths
- **Componentized UI**: A full set of reusable, accessible UI primitives (`/components/ui`).  
- **Hooks for logic**: Business logic for jobs, config, and sessions lives in hooks, reducing clutter in UI.  
- **Type safety**: TS improves maintainability.  

### Weaknesses / Problems
1. **Type Duplication**
   - `frontend/src/types/` has `api.ts` and `index.ts`.  
   - `index.ts` appears outdated/simplified compared to `api.ts`.  
   - Having two sources of truth for types risks drift and runtime errors.  

2. **`page.tsx` (Main Orchestrator)**
   - Currently overloaded with responsibilities:
     - Manages multiple hooks and their states (jobs, session, config).  
     - Controls frontpage visibility.  
     - Handles UI layout (dialogs, grids, theme toggling).  
   - This **mixes orchestration, state, and presentation** in a single file, making it hard to maintain.  

3. **`frontpage.tsx` (Marketing Page)**
   - Nearly empty; only defines a type.  
   - Doesn’t serve as a meaningful marketing/presentation component.  

4. **Styling**
   - Tailwind classes are long and repetitive, reducing readability.  
   - No central abstraction for shared styles (e.g., “primary button”, “card layout”).  
   - Marketing page variables exist in `globals.css` but aren’t fully leveraged.  
   - Responsiveness is handled ad hoc.  

---

## 2. Suggested Changes & Refactors

### A. Type Cleanup
- **Remove `frontend/src/types/index.ts`**.  
- Keep `api.ts` as the **single source of truth** for API data structures.  

---

### B. Refactor `page.tsx`
- **Problem:** Too much logic and layout in one place.  
- **Change:**  
  - Extract app logic and UI shell into a new **container component** (e.g., `InvoiceWorkspace.tsx`).  
  - `page.tsx` should only:
    - Decide whether to show `<Frontpage />` or `<InvoiceWorkspace />`.  
    - Pass down `onGetStarted` and any necessary props.  

**Before (simplified):**
```tsx
// page.tsx
// handles jobs, config, dialogs, layout, theme toggle, AND renders content
```

**After (simplified):**
```tsx
// page.tsx
'use client';
import { useJobs } from '@/hooks/useJobs';
import { Frontpage } from '@/components/marketing/frontpage';
import { InvoiceWorkspace } from '@/components/invoice-insights/invoice-workspace';

export default function Page() {
  const { jobs, results } = useJobs();
  const [showFrontpage, setShowFrontpage] = useState(true);

  useEffect(() => {
    if (jobs.length > 0 || results.length > 0) setShowFrontpage(false);
  }, [jobs, results]);

  return showFrontpage
    ? <Frontpage onGetStarted={() => setShowFrontpage(false)} />
    : <InvoiceWorkspace />;
}
```

---

### C. Refactor `frontpage.tsx`
- **Problem:** Empty placeholder, not a functional marketing component.  
- **Change:** Build it out as a **presentational component** only:
  - Hero section with tagline, subtext, and CTA button.  
  - Feature highlights.  
  - Accepts optional `limits` and an `onGetStarted` callback as props.  

**Example:**
```tsx
// frontpage.tsx
export function Frontpage({ limits, onGetStarted }: FrontpageProps) {
  return (
    <div className="marketing bg-texture-light dark:bg-texture-dark">
      <section className="text-center py-20">
        <h1 className="text-4xl font-bold">AI-Powered Invoice Processing</h1>
        <p className="text-lg mt-4 text-secondary-light dark:text-secondary-dark">
          Turn PDF invoices into structured data instantly.
        </p>
        <Button onClick={onGetStarted} className="mt-8">Get Started</Button>
      </section>
      <section className="py-16">
        {limits && <p>Upload up to {limits.maxFiles} files at once.</p>}
        {/* Feature cards */}
      </section>
    </div>
  );
}
```

---

### D. Styling Improvements
1. **Abstract common Tailwind styles**:
   - Use `clsx` or `tailwind-variants` to create reusable variants (`btn-primary`, `card-container`, `section-heading`).  
   - Example: `<Button variant="primary" />` instead of writing 5 utility classes each time.  

2. **Unify theme variables**:
   - Use values already in `globals.css` for consistent marketing + app UI.  
   - Define tokens for spacing, border radius, typography sizes.  

3. **Improve responsiveness systematically**:
   - Use `grid` or `flex` layouts consistently.  
   - Define breakpoints in `tailwind.config.ts` and apply them in reusable patterns.  

---

## 3. Expected Result / Target Structure

### Cleaner File Responsibilities
- `page.tsx` → Entry point, chooses between marketing and app workspace.  
- `frontpage.tsx` → Static marketing page, CTA-focused.  
- `InvoiceWorkspace.tsx` → Container for job/session/config orchestration, renders SmartHub, ResultsTable, dialogs, etc.  
- UI components → Smaller, testable, presentational.  

### Simplified State & Logic Flow
- Hooks (`useJobs`, `useConfig`, `useSession`) remain the source of truth.  
- `page.tsx` → orchestration (which screen to show).  
- `InvoiceWorkspace.tsx` → app UI + data orchestration.  

### Styling Improvements
- Consistent design language (colors, spacing, typography).  
- Shorter, more readable JSX (thanks to style abstractions).  
- Better responsiveness and theming alignment.  

---

👉 End result: **A frontend that is cleaner, more maintainable, and easier to extend**—with reduced duplication, separation of concerns, and a professional, consistent marketing experience.
