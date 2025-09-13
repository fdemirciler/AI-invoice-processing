# Message & Warning System Review

## 1. Current Situation

Your frontend currently has **three overlapping systems** for displaying messages and warnings:

1. **File upload warnings (rate limits, max 5 files, etc.)**
   - Implemented using **Radix UI Toasts** (`toast.tsx` + `toaster.tsx`).
   - Problem: toasts disappear instantly because `duration` was not configured (now fixed by adding `duration={5000}` to `ToastProvider`).

2. **Network/backend errors (blue/red messages at bottom-right)**
   - Implemented via custom `bannerMsg` / `bannerUntil` state inside `page.tsx`.
   - Styled using Tailwind + CSS variables from `globals.css`:
     - `--primary` (blue)
     - `--destructive` (red)
     - `--success` (green)
   - Looks good, but this is a **separate ad-hoc system**.

3. **Alert component**
   - Located at `frontend/src/components/ui/alert.tsx`.
   - Already supports **variants** (`default`, `destructive`, etc.) and uses the same theme colors.
   - Not consistently used by the other systems.

### Issues with current approach
- Multiple systems mean **inconsistent UX** and **duplicated logic**.
- Harder to maintain: errors/warnings can show in different styles and locations.
- No single source of truth for displaying messages.

---

## 2. Suggested Unified Solution

### Key Idea
Unify all warnings/errors (file upload limits, network errors, backend failures, success notices) into a **single message system** based on your existing **`Alert` component**.

### How it works
- Keep using the existing `useToast` hook for managing message state.
- Replace Radix `Toast` rendering with **`Alert` components**.
- Position alerts **above the file upload area** (instead of bottom-right).
- Use `variant` to control styling:
  - `default` → informational (blue)
  - `destructive` → errors (red)
  - `success` → confirmations (green)

### Example usage
```ts
// Show an error when too many files are uploaded
toast({
  variant: "destructive",
  title: "Upload limit exceeded",
  description: "You can only upload up to 5 files at once.",
})

// Show a network failure
toast({
  variant: "default",
  title: "Connection issue",
  description: "Could not reach the server. Please try again later.",
})

// Show a success message
toast({
  variant: "success",
  title: "Upload complete",
  description: "Your invoices have been uploaded successfully.",
})
```

### Benefits
- **Consistent styling** across all message types.
- **Single entry point** (`toast()`) for triggering messages.
- **Theme-aware** — automatically picks up your Tailwind + CSS variable colors.
- **Easier maintenance** — no need to juggle banner state, Radix Toasts, and alerts separately.

---

## 3. Implementation Plan

1. **Fix duration in `toaster.tsx`** (already done with `duration={5000}`).
2. **Create a new `MessageSystem.tsx`**:
   - Import `useToast`.
   - Map each toast to an `Alert` component.
   - Render alerts **above the file upload box** instead of bottom-right.
3. **Replace custom `bannerMsg` logic** in `page.tsx` with calls to `toast()`.
4. **Update error handling** in API calls to use `toast()` instead of direct DOM banners.

---

## 4. Next Step

Would you like me to draft the actual `MessageSystem.tsx` implementation that replaces both the `Toaster` and the `bannerMsg` logic?
