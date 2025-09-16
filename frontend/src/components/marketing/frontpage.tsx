"use client";

import React from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Upload, Zap, Download, Shield } from 'lucide-react';

type Limits = {
  maxFiles?: number;
  maxSizeMb?: number;
  maxPages?: number;
};

export function Frontpage({ limits, onStart }: { limits?: Limits; onStart: () => void }) {
  const maxFiles = limits?.maxFiles ?? '-';
  const maxSizeMb = limits?.maxSizeMb ?? '-';
  const maxPages = limits?.maxPages ?? '-';

  return (
    <div className="relative overflow-hidden bg-background" aria-label="frontpage">
      {/* Background Elements */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        {/* Geometric Circuit Pattern */}
        <svg
          className="absolute top-10 right-10 w-80 h-80 opacity-[0.06] text-foreground"
          viewBox="0 0 300 300"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        >
          <path d="M50 50 L50 100 L100 100 L100 150 L150 150" />
          <path d="M150 50 L150 100 L200 100 L200 150 L250 150" />
          <path d="M50 150 L100 150 L100 200 L150 200 L150 250" />
          <path d="M150 150 L200 150 L200 200 L250 200 L250 250" />
          <circle cx="50" cy="100" r="3" fill="currentColor" />
          <circle cx="100" cy="150" r="3" fill="currentColor" />
          <circle cx="150" cy="100" r="3" fill="currentColor" />
          <circle cx="200" cy="150" r="3" fill="currentColor" />
          <circle cx="150" cy="200" r="3" fill="currentColor" />
          <circle cx="250" cy="200" r="3" fill="currentColor" />
          <rect x="70" y="120" width="20" height="20" rx="2" fill="currentColor" opacity="0.3" />
          <rect x="170" y="70" width="20" height="20" rx="2" fill="currentColor" opacity="0.3" />
          <rect x="220" y="170" width="20" height="20" rx="2" fill="currentColor" opacity="0.3" />
        </svg>

        {/* Flowing Wave Pattern */}
        <svg
          className="absolute bottom-0 left-0 w-full h-40 opacity-[0.04] text-foreground"
          viewBox="0 0 1200 200"
          fill="none"
          preserveAspectRatio="none"
        >
          <path d="M0,100 C200,120 400,80 600,100 C800,120 1000,80 1200,100 L1200,200 L0,200 Z" fill="currentColor" />
          <path d="M0,120 C200,140 400,100 600,120 C800,140 1000,100 1200,120 L1200,200 L0,200 Z" fill="currentColor" opacity="0.5" />
        </svg>

        {/* Hexagonal Grid Pattern */}
        <svg
          className="absolute top-32 left-10 w-60 h-60 opacity-[0.05] text-foreground"
          viewBox="0 0 200 200"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.5"
        >
          <polygon points="50,20 80,35 80,65 50,80 20,65 20,35" />
          <polygon points="110,20 140,35 140,65 110,80 80,65 80,35" />
          <polygon points="170,20 200,35 200,65 170,80 140,65 140,35" />
          <polygon points="50,80 80,95 80,125 50,140 20,125 20,95" />
          <polygon points="110,80 140,95 140,125 110,140 80,125 80,95" />
          <polygon points="170,80 200,95 200,125 170,140 140,125 140,95" />
          <polygon points="50,140 80,155 80,185 50,200 20,185 20,155" />
          <polygon points="110,140 140,155 140,185 110,200 80,185 80,155" />
          <polygon points="170,140 200,155 200,185 170,200 140,185 140,155" />
        </svg>

        {/* Scattered Data Points */}
        <div className="absolute inset-0">
          <div className="absolute top-20 left-1/3 w-2 h-2 bg-primary rounded-full opacity-20" />
          <div className="absolute top-40 right-1/4 w-1 h-1 bg-primary rounded-full opacity-30" />
          <div className="absolute bottom-40 left-1/4 w-3 h-3 bg-primary rounded-full opacity-15" />
          <div className="absolute bottom-60 right-1/3 w-1.5 h-1.5 bg-primary rounded-full opacity-25" />
          <div className="absolute top-60 left-1/2 w-2 h-2 bg-primary rounded-full opacity-20" />
          <div className="absolute bottom-32 left-3/4 w-1 h-1 bg-primary rounded-full opacity-30" />
        </div>
      </div>

      {/* Hero Section */}
      <section className="container mx-auto px-6 pt-16 pb-8 md:py-20 relative">
        <div className="text-center max-w-4xl mx-auto">
          {/* Main Headline */}
          <div className="mb-6">
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-4">
              Transform Invoices into <span className="text-primary">Structured Data</span>
            </h1>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              Upload your PDF invoices and let AI automatically extract, organize, and export all the important data.
              Save hours of manual data entry.
            </p>
          </div>

          {/* CTA Section */}
          <div className="mb-16 md:mb-20">
            <Button size="lg" className="text-lg px-8 py-6 rounded-xl" onClick={onStart} aria-label="Start Processing Invoices">
              Start Processing Invoices
            </Button>
            <p className="text-sm text-muted-foreground mt-3">
              No signup required — Process up to <strong>{maxFiles}</strong> files free
            </p>
          </div>
        </div>
      </section>

      {/* Process Section */}
      <section className="py-12 md:py-20">
        <div className="container mx-auto px-6">
          <div className="text-center mb-10 md:mb-16">
            <h2 className="text-3xl font-bold mb-2 md:mb-4">How It Works</h2>
            <p className="text-lg text-muted-foreground">Three simple steps to transform your invoices</p>
          </div>

          <div className="max-w-5xl mx-auto">
            <div className="grid md:grid-cols-3 gap-6 md:gap-8">
              {/* Step 1 */}
              <Card className="p-8 text-center relative overflow-hidden">
                <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <Upload className="w-8 h-8 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-3">Upload</h3>
                <p className="text-muted-foreground mb-4">
                  Drag and drop your PDF invoices or click to browse.
                  Supports up to <strong>{maxFiles}</strong> files, <strong>{maxPages}</strong> pages each.
                </p>
                <div className="text-xs text-muted-foreground">PDF only • Max <strong>{maxSizeMb}</strong> MB per file</div>
              </Card>

              {/* Step 2 */}
              <Card className="p-8 text-center relative overflow-hidden">
                <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <Zap className="w-8 h-8 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-3">Process</h3>
                <p className="text-muted-foreground mb-4">
                  AI automatically extracts and organizes invoice details including amounts, dates, vendor info, and line items.
                </p>
                <div className="text-xs text-muted-foreground">Usually takes 5–15 seconds</div>
              </Card>

              {/* Step 3 */}
              <Card className="p-8 text-center relative overflow-hidden">
                <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <Download className="w-8 h-8 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-3">Export</h3>
                <p className="text-muted-foreground mb-4">
                  Review the extracted data and download as CSV. Perfect for importing into your accounting software.
                </p>
                <div className="text-xs text-muted-foreground">Excel & QuickBooks compatible</div>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* Privacy & Tech Section */}
      <section className="bg-muted/20 py-12 md:py-16">
        <div className="container mx-auto px-6">
          <div className="max-w-4xl mx-auto">
            <div className="grid md:grid-cols-2 gap-10 md:gap-12 text-center">
              {/* Privacy */}
              <div>
                <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Shield className="w-6 h-6 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-3">Privacy First</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Your files are processed securely and are automatically deleted once your session ends or when you clear data.
                  Nothing is stored permanently.
                </p>
              </div>

              {/* Technology */}
              <div>
                <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Zap className="w-6 h-6 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-3">Powered by AI</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Powered by Google Cloud Vision for OCR and Gemini AI for structured data extraction.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
