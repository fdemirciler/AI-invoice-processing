"use client";

import type { InvoiceDisplay } from '@/types/api';
import React, { useMemo, useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Download, ArrowUpDown, FileSpreadsheet } from 'lucide-react';
// no-op

interface ResultsTableProps {
  results: InvoiceDisplay[];
  onExport?: () => void;
}

type SortKey = 'invoiceNumber' | 'vendorName' | 'invoiceDate' | 'total';

export function ResultsTable({ results, onExport }: ResultsTableProps) {
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);

  const sortedResults = useMemo(() => {
    const items = [...results];
    if (!sortConfig) return items;
    const { key, direction } = sortConfig;
    const factor = direction === 'asc' ? 1 : -1;
    items.sort((a, b) => {
      if (key === 'total') {
        const av = a.total ?? 0;
        const bv = b.total ?? 0;
        return (av - bv) * factor;
      }
      const stringKey = key as 'invoiceNumber' | 'vendorName' | 'invoiceDate';
      const av = String((a[stringKey] ?? ''));
      const bv = String((b[stringKey] ?? ''));
      return av.localeCompare(bv) * factor;
    });
    return items;
  }, [results, sortConfig]);

  const requestSort = (key: SortKey) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const getSortIndicator = (key: SortKey) => {
    if (!sortConfig || sortConfig.key !== key) {
      return <ArrowUpDown className="ml-2 h-4 w-4 opacity-30" />;
    }
    return sortConfig.direction === 'asc' ? '▲' : '▼';
  };

  const handleExport = () => {
    if (onExport) return onExport();
    if (results.length === 0) return;
    // Fallback local export if onExport not provided
    const headers = ['Invoice Number', 'Vendor', 'Date', 'Total'];
    const csvRows = [
      headers.join(','),
      ...results.map(row => [
        `"${row.invoiceNumber}"`,
        `"${row.vendorName}"`,
        row.invoiceDate,
        row.total
      ].join(','))
    ];
    const csvString = csvRows.join('\n');
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'invoice_insights_export.csv');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
            <CardTitle className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5" />
                Invoice Data
            </CardTitle>
          <CardDescription>Review and export the data extracted from your invoices.</CardDescription>
        </div>
        <Button onClick={handleExport} disabled={results.length === 0} size="sm">
          <Download className="mr-2 h-4 w-4" />
          Export to CSV
        </Button>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                {(['invoiceNumber', 'vendorName', 'invoiceDate', 'total'] as SortKey[]).map(key => (
                   <TableHead key={key}>
                      <button className="flex items-center" onClick={() => requestSort(key)}>
                        {key === 'invoiceDate' ? 'Date' : key === 'vendorName' ? 'Vendor' : key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')}
                        <span className="ml-2">{getSortIndicator(key)}</span>
                      </button>
                    </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedResults.length > 0 ? (
                sortedResults.map((item: InvoiceDisplay, index: number) => (
                  <TableRow 
                    key={index} 
                    className="animate-fade-in-down"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <TableCell className="font-medium" style={{fontSize: '12px'}}>{item.invoiceNumber}</TableCell>
                    <TableCell style={{fontSize: '12px'}}>{item.vendorName}</TableCell>
                    <TableCell style={{fontSize: '12px'}}>{item.invoiceDate}</TableCell>
                    <TableCell className="text-right" style={{fontSize: '12px'}}>
                      {typeof item.total === 'number' ? `$${item.total.toFixed(2)}` : ''}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={4} className="h-48 text-center">
                    <div className="flex flex-col items-center justify-center text-muted-foreground">
                        <FileSpreadsheet className="w-12 h-12 mb-4" />
                        <p className="text-lg font-medium">No data to display.</p>
                        <p className="text-sm">Successfully processed invoices will show up here.</p>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
