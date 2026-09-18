// Fleet-wide wallpaper + kiosk accent colour push. Wallpaper reuses the same raw-upload +
// commit flow already used for Custom APK hosting (FilesResource's /raw + /update endpoints) —
// no new server-side upload surface needed. Both push as opaque agent commands
// (device.wallpaper / device.kioskTheme), same as every other device.* action.
import { apiClient } from './client';
import { bulkQueueCommand, type BulkCommandResult } from './commands';

export interface UploadedFileView {
  id?: number;
  filePath?: string;
  url?: string;
}

interface RawUploadResult {
  name: string;
  serverPath: string;
}

/** Upload an arbitrary file (no APK/icon-specific parsing or size constraints) to a server temp
 *  path — mirrors uploadApk()/commitUpload() in api/applications.ts, but via the /raw endpoint
 *  so a wallpaper image isn't run through APK metadata parsing. */
async function uploadRaw(file: File): Promise<RawUploadResult> {
  const form = new FormData();
  form.append('file', file, file.name);
  return apiClient.postForm<RawUploadResult>('/private/web-ui-files/raw', form);
}

/** Upload + host a wallpaper image, returning its served URL. */
export async function uploadWallpaper(file: File): Promise<string> {
  const up = await uploadRaw(file);
  const committed = await apiClient.post<UploadedFileView>('/private/web-ui-files/update', {
    tmpPath: up.serverPath,
    fileName: '',
    filePath: '',
    external: false,
  });
  if (!committed.url) throw new Error('Server could not host the image.');
  return committed.url;
}

export type WallpaperTarget = 'home' | 'lock' | 'both';

/** Push a hosted wallpaper to every device in the fleet. */
export async function pushWallpaperToAll(
  deviceIds: number[],
  url: string,
  target: WallpaperTarget,
): Promise<BulkCommandResult> {
  return bulkQueueCommand(deviceIds, {
    type: 'device.wallpaper',
    payload: JSON.stringify({ url, target }),
  });
}

/** Restyle every currently-kiosked device's status bar/exit chrome accent colour live, without
 *  re-picking apps. No-op on a device that isn't in kiosk right now. */
export async function pushKioskAccentToAll(
  deviceIds: number[],
  accentColor: string,
): Promise<BulkCommandResult> {
  return bulkQueueCommand(deviceIds, {
    type: 'device.kioskTheme',
    payload: JSON.stringify({ accentColor }),
  });
}
