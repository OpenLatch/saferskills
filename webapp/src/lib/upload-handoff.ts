// Homepage → /scan File handoff. A File can't survive an MPA navigation, so the
// homepage audit panel stashes the chosen File in IndexedDB (structured-clone
// stores File/Blob) under a one-time nonce, then navigates to
// `/scan#pending=<nonce>`; ScanConsole takes + deletes it on mount (P1-5).

import type { Visibility } from '@/lib/api/scans'

const DB_NAME = 'ss-upload-handoff'
const STORE = 'pending'
const VERSION = 1

export interface PendingUpload {
  file: File
  visibility: Visibility
}

function withStore<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('no-indexeddb'))
      return
    }
    const open = indexedDB.open(DB_NAME, VERSION)
    open.onupgradeneeded = () => open.result.createObjectStore(STORE)
    open.onerror = () => reject(open.error)
    open.onsuccess = () => {
      const db = open.result
      const tx = db.transaction(STORE, mode)
      const req = fn(tx.objectStore(STORE))
      req.onsuccess = () => resolve(req.result as T)
      req.onerror = () => reject(req.error)
      tx.oncomplete = () => db.close()
    }
  })
}

function makeNonce(): string {
  const a = new Uint8Array(12)
  crypto.getRandomValues(a)
  return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
}

/** Stash a File for the /scan handoff; returns the nonce to put in the URL hash. */
export async function stashPendingUpload(file: File, visibility: Visibility): Promise<string> {
  const nonce = makeNonce()
  await withStore('readwrite', (s) => s.put({ file, visibility }, nonce))
  return nonce
}

/** Take (and delete) a stashed File by nonce in one transaction. Null on miss. */
export async function takePendingUpload(nonce: string): Promise<PendingUpload | null> {
  try {
    return await withStore<PendingUpload | undefined>('readwrite', (s) => {
      const req = s.get(nonce)
      req.onsuccess = () => {
        if (req.result) s.delete(nonce)
      }
      return req
    }).then((rec) => rec ?? null)
  } catch {
    return null
  }
}
