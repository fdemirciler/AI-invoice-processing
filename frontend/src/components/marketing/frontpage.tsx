"use client";

import React from 'react';
import type { Limits } from '@/types/api';

export function Frontpage({ limits, onStart }: { limits?: Limits | null; onStart: () => void }) {
  const maxFiles = limits?.maxFiles ?? '-';
  const maxSizeMb = limits?.maxSizeMb ?? '-';
  const maxPages = limits?.maxPages ?? '-';

  return (
    <div className="marketing relative -mx-4 sm:-mx-6 lg:-mx-8 bg-texture-light bg-texture-dark" aria-label="frontpage">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <main className="py-16 md:py-24">
          <section className="text-center max-w-3xl mx-auto mb-24 md:mb-32">
            <h2 className="text-4xl md:text-6xl font-extrabold mb-6 tracking-tighter text-slate-900 dark:text-white">
              Transform Invoices into
              <span className="text-[var(--accent-color)]"> Structured Data</span>
            </h2>
            <p className="text-lg md:text-xl text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)] max-w-2xl mx-auto mb-10">
              Upload your PDF invoices and let AI automatically extract, organize, and export all the important data. Save hours of manual data entry.
            </p>
            <div className="flex flex-col sm:flex-row justify-center items-center gap-4">
              <button
                className="w-full sm:w-auto bg-[var(--accent-color)] text-white font-semibold py-3 px-8 rounded-full shadow-lg hover:bg-blue-700 transition-all duration-300 transform hover:-translate-y-1"
                onClick={onStart}
                aria-label="Start Processing Invoices"
              >
                Start Processing Invoices
              </button>
            </div>
            {typeof maxFiles === 'number' ? (
              <p className="text-sm text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)] mt-6">
                Process up to {maxFiles} files each time
              </p>
            ) : null}
          </section>

          <section className="text-center mb-24 md:mb-32">
            <h3 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">How It Works</h3>
            <p className="text-lg text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)] mb-16 max-w-xl mx-auto">Three simple steps to transform your invoices</p>
            <div className="grid md:grid-cols-3 gap-8">
              <div className="bg-[var(--surface-light)] dark:bg-[var(--surface-dark)] p-8 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm text-center transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                <div className="bg-blue-100 dark:bg-blue-900/30 inline-flex p-4 rounded-xl mb-6">
                  <span className="material-symbols-outlined text-[var(--accent-color)] text-3xl">upload_file</span>
                </div>
                <h4 className="text-xl font-semibold mb-2 text-slate-800 dark:text-slate-200">Upload</h4>
                <p className="text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)]">
                  Drag and drop your PDF invoices or click to browse. Supports up to {typeof maxFiles === 'number' ? maxFiles : '-'} files ({typeof maxPages === 'number' ? maxPages : '-'} pages each).
                </p>
                <p className="text-xs text-[var(--text-secondary-light)]/70 dark:text-[var(--text-secondary-dark)]/70 mt-4">PDF only • Max {typeof maxSizeMb === 'number' ? maxSizeMb : '-'} MB per file</p>
              </div>

              <div className="bg-[var(--surface-light)] dark:bg-[var(--surface-dark)] p-8 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm text-center transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                <div className="bg-blue-100 dark:bg-blue-900/30 inline-flex p-4 rounded-xl mb-6">
                  <span className="material-symbols-outlined text-[var(--accent-color)] text-3xl">bolt</span>
                </div>
                <h4 className="text-xl font-semibold mb-2 text-slate-800 dark:text-slate-200">Process</h4>
                <p className="text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)]">
                  AI automatically extracts and organizes invoice details including amounts, dates, vendor info, and line items.
                </p>
                <p className="text-xs text-[var(--text-secondary-light)]/70 dark:text-[var(--text-secondary-dark)]/70 mt-4">Usually takes 5-10 seconds</p>
              </div>

              <div className="bg-[var(--surface-light)] dark:bg-[var(--surface-dark)] p-8 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm text-center transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                <div className="bg-blue-100 dark:bg-blue-900/30 inline-flex p-4 rounded-xl mb-6">
                  <span className="material-symbols-outlined text-[var(--accent-color)] text-3xl">download</span>
                </div>
                <h4 className="text-xl font-semibold mb-2 text-slate-800 dark:text-slate-200">Export</h4>
                <p className="text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)]">
                  Review the extracted data and download as CSV. Use your invoice data in your analysis.
                </p>
                <p className="text-xs text-[var(--text-secondary-light)]/70 dark:text-[var(--text-secondary-dark)]/70 mt-4">CSV with full invoice data</p>
              </div>
            </div>
          </section>

          <section className="max-w-4xl mx-auto bg-[var(--surface-light)] dark:bg-[var(--surface-dark)] p-8 md:p-12 rounded-2xl border border-slate-100 dark:border-slate-800">
            <div className="grid md:grid-cols-2 gap-10 text-left">
              <div className="flex items-start space-x-4">
                <div className="bg-blue-100 dark:bg-blue-900/30 flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-xl">
                  <span className="material-symbols-outlined text-[var(--accent-color)]">privacy_tip</span>
                </div>
                <div>
                  <h4 className="text-lg font-semibold mb-1 text-slate-800 dark:text-slate-200">Privacy First</h4>
                  <p className="text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)]">
                    Your files are processed securely and are automatically deleted once your session ends or when you clear data. Nothing is stored permanently.
                  </p>
                </div>
              </div>
              <div className="flex items-start space-x-4">
                <div className="bg-blue-100 dark:bg-blue-900/30 flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-xl">
                  <span className="material-symbols-outlined text-[var(--accent-color)]">smart_toy</span>
                </div>
                <div>
                  <h4 className="text-lg font-semibold mb-1 text-slate-800 dark:text-slate-200">Powered by AI</h4>
                  <p className="text-[var(--text-secondary-light)] dark:text-[var(--text-secondary-dark)]">
                    Powered by Google Cloud Vision for OCR and Gemini AI for structured data extraction.
                  </p>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
