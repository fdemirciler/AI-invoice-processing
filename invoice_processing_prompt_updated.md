# Invoice Processing Web App Prompt

**<role>**  
You are an expert Python and web developer with strong experience in building cloud-native applications, integrating AI/LLM services, and designing modern, minimal frontend UIs. You have deep knowledge of Google Cloud Platform services and their free-tier limits, as well as best practices for building secure and scalable web applications.  
**</role>**  

**<goal>**  
I want to build a single-page web application (SPA) that processes invoices end-to-end using services/tools from Google Cloud that are offered with free-tier. The workflow is as follows:  

1. **File Upload** – User can upload one or multiple invoice PDFs at a time.  
2. **OCR Extraction** – Backend sends the files to **Google Vision AI** to extract raw text and/or structured document data.  
3. **Data Processing** – Extracted data is processed via a Python-based intermediary pipeline (e.g., regex cleaning, parsing, or pre-formatting for LLM input).  
4. **LLM Integration** – The cleaned data is passed to an LLM (Gemini via Google AI Studio or OpenRouter API). The LLM returns structured invoice information as **key-value pairs** (e.g., invoice number, date, vendor, line items, totals).  
5. **Frontend Display** – Structured output for all processed invoices is displayed in a clean, responsive table in the frontend. Each invoice can be viewed individually or in a combined results table.  
6. **Export** – User can download structured results as **CSV files** (one CSV per invoice or a combined CSV).  

This project is primarily a **practice project** to explore how LLMs can be integrated into a document-processing workflow using modern web technologies.  

**</goal>**  

**<constraints>**  
- **Platform & Tools:** Must use **Google Cloud free tier services** wherever possible. (See: https://cloud.google.com/free?hl=en)  
- **Backend:** Should be implemented in **Python** with **FastAPI** (open to alternatives if they simplify deployment on GCP). Must include:  
  - Multi-file upload support (parallel or sequential processing).  
  - File size limit per upload (configurable, e.g., max 10MB per file).  
  - Maximum number of pages per invoice (configurable, e.g., 20 pages).  
  - Restrict uploads to **PDF only**.  
  - Integration with Google Vision API.  
  - Preprocessing pipeline before sending data to LLM (strip headers, irrelevant text, compress whitespace).  
  - Async processing: files must be queued and processed asynchronously to avoid blocking the frontend.  
  - Stream PDF directly from the upload request to Vision (FastAPI’s UploadFile) to avoid temporary disk storage.  
  - Integration with Gemini (or OpenRouter if Gemini isn’t feasible).  
  - Rate limiting.  
  - CORS support.  
  - **File deletion:** invoice files must be deleted immediately after processing (do not rely on lifecycle rules).  
- **Frontend:**  
  - Single-page app (React build supported).  
  - Modern, minimal, responsive design.  
  - File upload component (supporting multiple files).  
  - Display processing **status per file**: `Uploaded → Processing → Extracting → Done`.  
  - Display extracted data in a table (per invoice or combined view).  
  - CSV download option.  
  - Retry button to allow re-processing failed files.  
  - Optional dark mode support.  
  - Session ends on browser refresh (no user management).  
- **Deployment:** Should run fully on Google Cloud free tier services (Cloud Run, Cloud Functions, Firebase Hosting, etc.).  
- **Security & Reliability:**  
  - File validation (type, size, page limit) enforced both on frontend and backend.  
  - Basic error handling (failed uploads, Vision API failures, LLM timeout).  
  - Input size limitations and rejection with clear error messages.  
  - API key management best practices.  
- **Internationalization:**  
  - Vision AI must support **multi-language invoices**. Invoices will primarily be in **Dutch and English**.  

**</constraints>**  

# Roadmap

## ✅ MVP (Minimum Viable Product)
1. Frontend (React + Firebase Hosting)  
   - Multi-file PDF upload with size + page limit validation.  
   - Show file status: `Uploaded → Processing → Extracting → Done`.  
   - Responsive, minimal UI with results displayed in a table.  
   - CSV download option.  
2. Backend (FastAPI on Cloud Run)  
   - File upload endpoint with validation.  
   - Async job queue to process files without blocking.  
   - Integration with Google Vision API for OCR.  
   - Pre-process text before LLM.  
   - Send processed text to LLM (Gemini or OpenRouter).  
   - Return structured key-value pairs back to frontend.  
   - Delete files immediately after processing.  
3. Security  
   - Enforce CORS (frontend domain only).  
   - Store API keys in Secret Manager.  
   - HTTPS enforced (Firebase + Cloud Run).  
4. Internationalization  
   - Configure Vision AI to handle Dutch + English invoices.  

## 🔜 Later Enhancements (Nice-to-Have)
- User-friendly error messages and retry for transient failures.  
- Combined CSV export for multiple invoices.  
- Smarter pre-cleaning before LLM to reduce token cost.  
- Drag-and-drop uploader and progress bars.  
- Logging for API usage and errors.  
- Optional Firebase Auth if you want to restrict app usage.  
- Dark mode support.  
- Future scalability (Pub/Sub or Cloud Tasks for large batch processing).  
