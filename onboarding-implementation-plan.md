# Onboarding Implementation Plan for AI Invoice Processing

This document describes how to implement a simple, modern, and sleek onboarding experience for your **AI Invoice Processing** app, consistent with your existing design system (TailwindCSS + ShadCN).

---

## 🎯 Goals
- Clearly explain **what the app does** and **how to use it** upon landing.
- Keep the interface **minimal and consistent** with the current design.
- Provide **information on demand** without cluttering the upload workflow.
- Ensure **scalability** for future features.

---

## 🖼️ Flow Overview

1. **Hero Section (Landing Header)**  
   - Display a **title** and **tagline** directly above the upload area.  
   - Immediately communicates purpose.

2. **How It Works (3-Step Guide)**  
   - Shown **below the upload area** in a 3-column layout.  
   - Uses icons + short benefit-driven text.

3. **Help Modal (Information on Demand)**  
   - Accessed via a **Help icon** (`HelpCircle`) in the top-right header.  
   - Opens a modal with **accordion sections** for:  
     - Usage Limits  
     - Privacy & Security  
     - Technology  

4. **Empty State (Optional Enhancement)**  
   - When no jobs are uploaded, display a **welcome message** above the upload box.  
   - Disappears after first upload.

---

## 🧩 Components

### Hero Section
- **Component**: `Card` (ShadCN) or simple `div` with Tailwind.  
- **Placement**: Above `<SmartHub />` upload component.  
- **Content**:  
  ```tsx
  <div className="text-center space-y-2">
    <h1 className="text-3xl font-bold tracking-tight text-foreground">AI Invoice Processing</h1>
    <p className="text-muted-foreground">Turn your PDF invoices into structured data, ready for export.</p>
  </div>
  ```

---

### How It Works (3-Step Guide)
- **Component**: Flexbox or Grid (3 cols on desktop, 1 col on mobile).  
- **Styling**: Use `Card` or `div` with Tailwind utility classes.  
- **Layout**:  
  ```tsx
  <div className="grid gap-6 md:grid-cols-3 mt-8">
    <Card className="p-4 text-center">
      <div className="flex justify-center mb-2 text-primary">
        <UploadCloud className="h-6 w-6" />
      </div>
      <h3 className="font-semibold">1. Upload</h3>
      <p className="text-sm text-muted-foreground">Drag and drop your PDF invoices to get started.</p>
    </Card>
    <Card className="p-4 text-center">
      <div className="flex justify-center mb-2 text-primary">
        <Sparkles className="h-6 w-6" />
      </div>
      <h3 className="font-semibold">2. Process</h3>
      <p className="text-sm text-muted-foreground">AI automatically extracts and organizes your invoice details.</p>
    </Card>
    <Card className="p-4 text-center">
      <div className="flex justify-center mb-2 text-primary">
        <FileSpreadsheet className="h-6 w-6" />
      </div>
      <h3 className="font-semibold">3. Export</h3>
      <p className="text-sm text-muted-foreground">Review results and export them instantly as CSV.</p>
    </Card>
  </div>
  ```

---

### Help Modal
- **Trigger**: `HelpCircle` icon in header (top-right).  
- **Component**: `Dialog` or `Sheet` from ShadCN.  
- **Content**: Use `Accordion` for structured info.  

```tsx
<Dialog>
  <DialogTrigger asChild>
    <Button variant="ghost" size="icon">
      <HelpCircle className="h-5 w-5" />
    </Button>
  </DialogTrigger>
  <DialogContent className="max-w-lg">
    <DialogHeader>
      <DialogTitle>About This App</DialogTitle>
    </DialogHeader>
    <Accordion type="single" collapsible className="mt-4">
      <AccordionItem value="limits">
        <AccordionTrigger>Usage Limits</AccordionTrigger>
        <AccordionContent>
          File uploads are limited by your plan. Current limits:
          - Max files per upload: **{maxFiles}**
          - Max file size: **{maxSizeMb} MB**
          - Max pages per PDF: **{maxPages}**
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="privacy">
        <AccordionTrigger>Privacy & Security</AccordionTrigger>
        <AccordionContent>
          Your files are processed securely in the cloud. They are automatically deleted after your session ends or when you clear data manually.
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="tech">
        <AccordionTrigger>Technology</AccordionTrigger>
        <AccordionContent>
          Powered by <strong>Google Cloud Vision</strong> for OCR and <strong>Gemini AI</strong> for structured data extraction.
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  </DialogContent>
</Dialog>
```

---

## 🎨 Styling Guidelines (Tailwind + ShadCN)

- **Colors**: Use `text-foreground`, `text-muted-foreground`, and `text-primary` consistently.  
- **Spacing**: Use `space-y-2`, `mt-8`, `p-4` for consistent rhythm.  
- **Typography**:  
  - Title: `text-3xl font-bold tracking-tight`  
  - Subtext/Tagline: `text-muted-foreground`  
  - Step headings: `font-semibold`  
  - Step descriptions: `text-sm text-muted-foreground`  

---

## ✨ Final Polished Copy

### Hero Section
**Title**: AI Invoice Processing  
**Tagline**: Turn your PDF invoices into structured data, ready for export.

### How It Works (3 Steps)
1. **Upload**: Drag and drop your PDF invoices to get started.  
2. **Process**: AI automatically extracts and organizes your invoice details.  
3. **Export**: Review results and download them instantly as a CSV file.

### Help Modal
- **Usage Limits**:  
  - Upload up to **{maxFiles}** files at once.  
  - Each file can be up to **{maxSizeMb} MB**.  
  - Maximum of **{maxPages}** pages per invoice.  

- **Privacy & Security**:  
  Your files are processed securely and are automatically deleted once your session ends or when you clear data. Nothing is stored permanently.  

- **Technology**:  
  Powered by **Google Cloud Vision** for OCR and **Gemini AI** for structured data extraction.  

---

## ✅ Next Steps
1. Implement the **Hero + Tagline** section in `page.tsx`.  
2. Add the **3-step guide** using existing `Card` components.  
3. Insert a **Help icon** into your header, linking it to a `Dialog` with `Accordion`.  
4. Apply consistent Tailwind + ShadCN styling for sleek, modern UX.  
