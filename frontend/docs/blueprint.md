# **App Name**: Invoice Insights

## Core Features:

- File Upload with Validation: Enable users to upload PDF invoices with client-side validation for file type, size, and count, based on configurations fetched from the API.
- Real-Time Job Dashboard: Display a dashboard with a list of uploaded files, their filenames, and processing status (e.g., 'Processing', 'Done', 'Failed'), updating in real-time via polling.
- Retry Failed Jobs: Allow users to retry failed invoice processing jobs via a 'Retry' button on the job dashboard.
- Structured Data Display: Present the extracted data from successfully processed invoices in a sortable table, including key fields such as Invoice Number, Vendor, Date, and Total.
- CSV Export: Provide a single-click button to download all results from the current session as a single CSV file.
- Session Management: Enable users to clear all session data from the server and reset the UI using a 'Clear Session' button.

## Style Guidelines:

- Primary color: A vibrant, slightly desaturated blue (#64B5F6) to convey trust and professionalism, evoking the sensation of digitized information.
- Background color: A very light, desaturated blue (#F0F8FF) to ensure readability and a clean interface.
- Accent color: A contrasting amber (#FFC107) to draw attention to important actions and status indicators.
- Headline font: 'Space Grotesk' sans-serif for a computerized feel.
- Body font: 'Inter' sans-serif with a modern look, suitable for large blocks of text.
- Use minimalist and clear icons to represent file types, statuses, and actions.
- Employ a clean, modern layout with clear separation between the file upload area, job dashboard, and results table.