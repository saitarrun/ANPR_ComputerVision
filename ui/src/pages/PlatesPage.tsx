import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { PlateResponse } from '../lib/api';
import { platesAPI } from '../lib/api';

export const PlatesPage = () => {
  const [limit, setLimit] = useState(50);
  const [searchPlate, setSearchPlate] = useState('');
  const [sortBy, setSortBy] = useState<'recent' | 'frequent'>('recent');

  const { data: plates = [], isLoading } = useQuery<PlateResponse[]>({
    queryKey: ['plates', limit],
    queryFn: async () => {
      const response = await platesAPI.list({ limit });
      return response.data;
    },
  });

  // Filter and sort locally
  const filteredPlates = plates
    .filter((p) => p.plate_string.toUpperCase().includes(searchPlate.toUpperCase()))
    .sort((a, b) => {
      if (sortBy === 'frequent') {
        return b.detection_count - a.detection_count;
      }
      return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
    });

  return (
    <div className="p-8">
      <div className="mb-6 space-y-4">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">
          Detected License Plates
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Search */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Search Plate
            </label>
            <input
              type="text"
              placeholder="e.g., ABC123"
              value={searchPlate}
              onChange={(e) => setSearchPlate(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="plate-search"
            />
          </div>

          {/* Sort */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Sort By
            </label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'recent' | 'frequent')}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
            >
              <option value="recent">Most Recent</option>
              <option value="frequent">Most Frequent</option>
            </select>
          </div>

          {/* Limit */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Show
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
            >
              <option value={10}>10</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={500}>500</option>
            </select>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          Loading plates...
        </div>
      ) : filteredPlates.length === 0 ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          {plates.length === 0 ? 'No plates detected yet' : 'No plates match your search'}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Plate
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Region
                </th>
                <th className="px-6 py-3 text-right font-medium text-slate-700 dark:text-slate-300">
                  Detections
                </th>
                <th className="px-6 py-3 text-right font-medium text-slate-700 dark:text-slate-300">
                  Avg. Confidence
                </th>
                <th className="px-6 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                  Last Seen
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {filteredPlates.map((plate) => (
                <tr
                  key={plate.id}
                  className="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  data-testid={`plate-row-${plate.id}`}
                >
                  <td className="px-6 py-4 font-mono font-semibold text-slate-900 dark:text-white">
                    {plate.plate_string}
                  </td>
                  <td className="px-6 py-4 text-slate-700 dark:text-slate-300">
                    {plate.region_id}
                  </td>
                  <td className="px-6 py-4 text-right text-slate-700 dark:text-slate-300">
                    {plate.detection_count}
                  </td>
                  <td className="px-6 py-4 text-right text-slate-700 dark:text-slate-300">
                    {(plate.avg_confidence * 100).toFixed(1)}%
                  </td>
                  <td className="px-6 py-4 text-xs text-slate-600 dark:text-slate-400">
                    {new Date(plate.last_seen_at).toLocaleString()}
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
