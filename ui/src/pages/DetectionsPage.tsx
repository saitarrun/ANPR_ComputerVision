import { useQuery } from '@tanstack/react-query';
import type { DetectionResponse } from '../lib/api';
import { detectionAPI } from '../lib/api';

export const DetectionsPage = () => {
  const { data: detections = [], isLoading } = useQuery<DetectionResponse[]>({
    queryKey: ['detections'],
    queryFn: async () => {
      const response = await detectionAPI.list({ limit: 100 });
      return response.data;
    },
  });

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-6">
        Recent Detections
      </h2>

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
                  ID
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Camera
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Plate
                </th>
                <th className="px-6 py-3 text-right font-medium text-slate-700 dark:text-slate-300">
                  Plate Conf.
                </th>
                <th className="px-6 py-3 text-right font-medium text-slate-700 dark:text-slate-300">
                  Char Conf.
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
                  <td className="px-6 py-4 text-slate-900 dark:text-white font-mono text-xs">
                    {detection.id}
                  </td>
                  <td className="px-6 py-4 text-slate-700 dark:text-slate-300">
                    {detection.camera_id}
                  </td>
                  <td className="px-6 py-4 font-mono font-semibold text-slate-900 dark:text-white">
                    {detection.raw_plate}
                  </td>
                  <td className="px-6 py-4 text-right text-slate-700 dark:text-slate-300">
                    {(detection.plate_confidence * 100).toFixed(1)}%
                  </td>
                  <td className="px-6 py-4 text-right text-slate-700 dark:text-slate-300">
                    {(detection.char_confidence * 100).toFixed(1)}%
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
