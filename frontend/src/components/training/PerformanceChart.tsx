
import React from 'react';
import { ModelPerformanceDataPoint } from '../../types.ts';
import Card from '../ui/Card.tsx';

interface PerformanceChartProps {
  data: ModelPerformanceDataPoint[];
}

const PerformanceChart: React.FC<PerformanceChartProps> = ({ data }) => {
  const width = 500;
  const height = 250;
  const padding = { top: 20, right: 20, bottom: 30, left: 40 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const yMin = Math.min(...data.map(d => d.accuracy));
  const yMax = Math.max(...data.map(d => d.accuracy));
  const yRange = yMax - yMin;

  const xScale = (index: number) => padding.left + (index / (data.length - 1)) * chartWidth;
  const yScale = (value: number) => padding.top + chartHeight - ((value - yMin) / yRange) * chartHeight;

  const linePath = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(d.accuracy)}`).join(' ');
  const areaPath = `${linePath} L ${xScale(data.length - 1)} ${height - padding.bottom} L ${padding.left} ${height - padding.bottom} Z`;

  return (
    <Card className="p-4 sm:p-6 h-full">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" aria-labelledby="perf-chart-title" role="img">
        <title id="perf-chart-title">Model performance accuracy over the last 7 training cycles.</title>
        <defs>
          <linearGradient id="perfAreaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
          </linearGradient>
        </defs>
        
        <path d={areaPath} fill="url(#perfAreaGradient)" />
        <path d={linePath} fill="none" stroke="#10b981" strokeWidth="2.5" />

        {data.map((d, i) => (
          <g key={i}>
            <circle cx={xScale(i)} cy={yScale(d.accuracy)} r="4" fill="#10b981" />
            <text x={xScale(i)} y={height - padding.bottom + 15} textAnchor="middle" fill="#9ca3af" fontSize="12">
              {d.date}
            </text>
          </g>
        ))}
        
        {[0, 0.5, 1].map(tick => (
          <text key={tick} x={padding.left - 8} y={yScale(yMin + tick * yRange)} textAnchor="end" alignmentBaseline="middle" fill="#9ca3af" fontSize="12">
            {(yMin + tick * yRange).toFixed(3)}
          </text>
        ))}
      </svg>
    </Card>
  );
};

export default PerformanceChart;
