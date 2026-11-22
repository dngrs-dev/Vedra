import { useState } from 'react';
import { PrinterIcon } from '@/components/ui/Icons';
import { toast } from '@/components/ui/toastStore';
import { pl } from '@/constants/pl';
import { downloadFile } from '@/services/http';

/** Downloads a report PDF, showing progress while the server renders it and a message if it fails. */
export function PdfDownloadButton({ href, label, fileName }: { href: string; label: string; fileName: string }) {
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      await downloadFile(href, fileName);
    } catch (e) {
      toast(e instanceof Error && e.message ? e.message : pl.error.unknown, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <button type="button" className="btn-primary no-print" disabled={busy} aria-busy={busy} onClick={() => void download()}>
      <PrinterIcon /> {busy ? pl.report.downloading : label}
    </button>
  );
}
