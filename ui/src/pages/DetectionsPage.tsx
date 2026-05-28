import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { DetectionResponse } from '../lib/api';
import { detectionAPI } from '../lib/api';

export const DetectionsPage = () => {
  const [limit, setLimit] = useState(100);

  const { data: detections = [], isLoading } = useQuery<DetectionResponse[]>({
    queryKey: ['detections', limit],
    queryFn: async () => {
      const response = await detectionAPI.list({ limit });
      return response.data;
    },
  });

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">
          Recent Detections
        </h2>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Show:
          </label>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
          >
            <option value={10}>10</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={500}>500</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          Loading detections...
        </div>
      ) : detections.length === 0 ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          No detections yet
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Camera
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Plate ID
                </th>
                <th className="px-6 py-3 text-right font-medium text-slate-700 dark:text-slate-300">
                  Confidence
                </th>
                <th className="px-6 py-3 text-right font-medium text-slate-700 dark:text-slate-300">
                  Quality
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  OCR Backend
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Timestamp
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {detections.map((detection) => (
                <tr
                  key={detection.id}
                  className="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  data-testid={`detection-row-${detection.id}`}
                >
                  <td className="px-6 py-4 text-slate-700 dark:text-slate-300 text-xs font-mono">
                    {detection.camera_id.substring(0, 8)}...
                  </td>
                  <td className="px-6 py-4 font-mono font-semibold text-slate-900 dark:text-white text-xs">
                    {detection.plate_id.substring(0, 8)}...
                  </td>
                  <td className="px-6 py-4 text-right text-slate-700 dark:text-slate-300">
                    {(detection.confidence * 100).toFixed(1)}%
                  </td>
                  <td className="px-6 py-4 text-right text-slate-700 dark:text-slate-300">
                    {(detection.quality_score * 100).toFixed(1)}%
                  </td>
                  <td className="px-6 py-4 text-slate-700 dark:text-slate-300 text-xs">
                    {detection.ocr_backend}
                  </td>
                  <td className="px-6 py-4 text-xs text-slate-600 dark:text-slate-400">
                    {new Date(detection.frame_timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
