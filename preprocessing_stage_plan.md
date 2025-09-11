# **Implementation Plan: Adaptive Preprocessing Pipeline**

This document outlines the detailed implementation plan for re-architecting the invoice processing pipeline's preprocessing stage. It is designed to serve as a complete blueprint for development.

## **1\. Project Overview & Scope**

### **Project Goal**

To implement an adaptive and resilient preprocessing pipeline that intelligently minimizes the OCR output from Google Vision AI before sending it to a Large Language Model (LLM). The primary objective is to drastically reduce API costs and processing latency while improving extraction accuracy by providing the LLM with a clean, high-signal, and contextually complete payload.

### **Scope Boundaries**

* **Included**:  
  * Simplifying the OCR stage to *always* use the Google Vision API (synchronous for short PDFs, asynchronous for long ones).  
  * Implementing a new PreprocessorService in Python.  
  * Building a Document Object Model (DOM) from the Vision API's full JSON response, including text, coordinates, and confidence scores.  
  * Implementing **dynamic zone detection** based on vertical gaps.  
  * Implementing **context-aware confidence filtering**.  
  * Implementing a **hybrid table summarizer** with a robust fallback mechanism.  
  * Handling multi-page documents on a page-by-page basis for the initial version (V1).  
* **Explicitly Excluded (Future Enhancements)**:  
  * Complex clustering algorithms (e.g., K-Means) for zone detection. The V1 will use a simpler, pragmatic gap-finding method.  
  * Advanced logic for parsing tables that span across multiple pages.  
  * A machine learning feedback loop to dynamically tune thresholds based on LLM success rates.

### **Success Criteria**

1. **Performance**: Achieve a **\>60% average reduction** in the token count of the payload sent to the LLM compared to the raw OCR text.  
2. **Accuracy**: The final extraction accuracy for key fields (vendor, date, total) must be equal to or greater than the baseline of using the unprocessed text.  
3. **Reliability**: The pipeline must successfully process at least 99% of sample invoices without catastrophic data loss, correctly utilizing the fallback mechanism for unrecognized table formats.  
4. **Latency**: The end-to-end processing time for a typical 1-2 page invoice should be **reduced by at least 30%**.

### **Target Users**

The system will be used by the backend application (tasks.py worker) to automatically process PDF invoices uploaded by end-users through the web interface.

## **2\. Architecture & Design Principles**

### **Configuration Management**

All tunable parameters (thresholds, keywords, feature flags) will be externalized and managed via the existing config.py module, which loads from environment variables. This allows for easy tuning and experimentation without code changes.

### **Code Quality Standards**

* **Modularity**: Functionality will be broken into small, focused modules and functions.  
* **Single Responsibility**: Each function and class will have one clear purpose.  
* **Maintainability**: The implementation will prioritize simple, pragmatic solutions with robust error handling over premature or overly complex optimizations.

## **3\. Implementation Structure: Preprocessing Workflow**

The new workflow inserts an intelligent PreprocessorService between the OCR and LLM stages.

### **Core Components**

#### **Component: dom.py (Document Object Model)**

* **Purpose**: To provide a clean, structured, in-memory representation of the invoice, transforming the raw Vision API JSON into intuitive Python objects. This is the foundation for all subsequent processing.  
* **Input Requirements**: N/A (Defines data structures).  
* **Processing Logic**: Defines dataclasses for Document, Page, Block, Line, Word, and BoundingBox. These classes will include fields for text, bounding\_box coordinates, and OCR confidence.  
* **Output Format**: A set of classes to be used by the PreprocessorService.

#### **Component: PreprocessorService**

* **Purpose**: To orchestrate the entire preprocessing pipeline, from DOM construction to final payload generation. It acts as an intelligent compression and sanitization layer.  
* **Input Requirements**: The full, raw JSON response object from the VisionService.  
* **Output Format**: A single, pruned str payload ready for the LLMService.

### **Sub-Components & Modules (Internal Pipeline of the PreprocessorService)**

#### **1\. DOM Construction Module**

* **Responsibility**: To parse the raw Vision API JSON into our structured Document object.  
* **Processing Logic**:  
  1. Iterate through the pages, blocks, paragraphs, lines, and words in the JSON.  
  2. Populate our custom DOM dataclasses with their respective text, coordinates, and confidence scores.  
  3. Calculate and store the average confidence for each parent element (Line and Block) based on its children.  
* **Output**: A fully hydrated Document object.

#### **2\. Dynamic Zone Detection Module**

* **Responsibility**: To replace rigid percentage-based zones with an adaptive method that understands the document's layout.  
* **Processing Logic**:  
  1. For each Page in the DOM, get all Block objects, sorted vertically.  
  2. Calculate the vertical distance (gap) between each adjacent block.  
  3. Identify the largest gaps to define the boundaries of the **Header**, **Body**, and **Footer** zones dynamically.  
* **Error Scenarios**: If a page has too few blocks to find meaningful gaps, the entire page will be treated as a single "Body Zone" as a fallback.

#### **3\. Context-Aware Confidence Filtering Module**

* **Responsibility**: To surgically remove OCR noise without deleting critical data.  
* **Processing Logic**:  
  1. **Global Noise Removal**: First, perform a pass over the entire DOM and remove any Word with a very low confidence score (e.g., \< 0.5).  
  2. **Zone-Based Filtering**: After dynamic zoning, apply a more conservative filter. A standard threshold (e.g., \> 0.7) is applied to the Header and Body zones. The critical **Footer Zone** (containing totals) will have a much lower threshold or be left unfiltered entirely.  
* **Data Flow**: The Document object is modified in-place, now containing only high-confidence text.

#### **4\. Hybrid Table Handling Module**

* **Responsibility**: To drastically reduce tokens from line items while preserving essential context for the LLM, with a safety net for unknown formats.  
* **Processing Logic**:  
  1. **Table Detection**: Analyze the **Body Zone** to detect a table by looking for multiple consecutive lines with words that have similar X-coordinates (indicating columns).  
  2. **On Success \-\> Hybrid Payload**: If a table is confidently detected, generate a **hybrid summary**. This includes the *actual* text of the table's column headers and final summary rows (subtotal, tax, total), but replaces the inner line items with a simple summary string (e.g., ...\[5 line items summarized\]...).  
  3. **On Failure \-\> Fallback**: If a coherent table is not found, **do not summarize**. Fall back to using the **full, cleaned text of the entire Body Zone**.  
* **Output**: Either a hybrid table string or the full, cleaned text of the Body Zone.

#### **5\. Payload Assembly Module**

* **Responsibility**: To combine the processed data from all pages into a single, coherent payload for the LLM.  
* **Processing Logic**:  
  1. The pipeline runs on each Page in the Document object independently.  
  2. The final payload is a single string, concatenating the processed zones from all pages in order, separated by a clear marker (e.g., \--- Page 2 \---).  
  3. A final sanitization pass removes any redundant whitespace from the combined string.  
* **Data Flow**: The final string is the output of the PreprocessorService and the input for the LLMService.

## **4\. Implementation Phases**

#### **Phase 1: Foundation & DOM Construction**

* **Deliverables**:  
  1. Create dom.py with the finalized data classes.  
  2. Update the VisionService to return the full Vision API JSON response.  
  3. Implement the build\_dom method in the new PreprocessorService.  
* **Success Criteria**: The PreprocessorService can successfully create a complete Document object from a sample Vision API JSON file.

#### **Phase 2: Dynamic Zoning & Filtering**

* **Deliverables**:  
  1. Implement the **Dynamic** Zone Detection logic based on vertical gaps.  
  2. Implement the **Context-Aware Confidence Filtering** logic.  
* **Success Criteria**: The service can correctly segment a sample invoice into Header, Body, and Footer zones and apply different confidence filters to each.

#### **Phase 3: Table Handling & Final Integration**

* **Deliverables**:  
  1. Implement the **Hybrid Table Handling** logic, including the parser and the crucial fallback mechanism.  
  2. Implement the final payload assembly and sanitization logic.  
  3. Integrate the fully functional PreprocessorService into the tasks.py worker.  
* **Success Criteria**: The end-to-end pipeline successfully processes sample invoices, demonstrating significant token reduction and correct fallback behavior.

#### **Phase 4: Monitoring & Refinement**

* **Deliverables**:  
  1. Add logging to record key metrics (e.g., token reduction percentage, which fallback was used).  
  2. Deploy the new service to production and monitor its performance and accuracy on real-world invoices.  
* **Success Criteria**: The system runs stably in production and meets the project's overall success criteria.

## **5\. Risk Assessment & Mitigation**

* **Risk**: The custom table parsing logic may be complex and fail on unconventional layouts.  
  * **Mitigation**: The **fallback mechanism is our primary defense**. By defaulting to the full body text when parsing fails, we ensure data integrity is prioritized over token reduction. The V1 parser will be kept simple and can be iterated on in the future.  
* **Risk**: Dynamic zoning may fail on invoices with very unusual graphic layouts.  
  * **Mitigation**: The gap-finding logic is more robust than fixed percentages. A fallback that treats the entire page as a single "Body Zone" will prevent crashes and ensure all text is still processed.  
* **Risk**: Maintenance overhead for a custom parser.  
  * **Mitigation**: This is an accepted trade-off for achieving high reliability. The modular