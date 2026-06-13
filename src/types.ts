export interface JobStatus {
  id: string;
  type: 'text-to-video' | 'image-to-video';
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: string;
  videoUrl: string | null;
  error: string | null;
  screenshots?: string[];
  createdAt: number;
}

export interface ServiceStatus {
  status: string;
  ngrokUrl: string;
  ngrokEnabled: boolean;
}

export type ActiveTab = 'text-to-video' | 'image-to-video';
