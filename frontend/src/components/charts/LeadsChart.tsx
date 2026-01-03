
import React, { useState, useMemo } from 'react';
import { ChartDataPoint } from '../../types.ts';
import Card from '../ui/Card.tsx';

interface LeadsChartProps {
  data: ChartDataPoint[];
  loading: boolean;
}

const LeadsChart: React.FC<LeadsChartProps> = ({ data, loading }) => {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; data: ChartDataPoint } | null>(null);

  const width = 600;
  const height = 300;
  const padding = { top: 20, right: 20, bottom: 40, left: 40 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const { xScale, yScale, yMax, linePathLeads, linePathAppointments, areaPathLeads, areaPathAppointments, points } = useMemo(() => {
    if (!data || data.length === 0) {
      return { xScale: null, yScale: null, yMax: 0, linePathLeads: '', linePathAppointments: '', areaPathLeads: '', areaPathAppointments: '', points: [] };
    }
    
    const yMax = Math.ceil((Math.max(...data.map(d => d.leads), ...data.map(d => d.appointments)) * 1.2) / 5) * 5 || 10;

    const xScale = (index: number) => padding.left + (index / (data.length - 1)) * chartWidth;
    const yScale = (value: number) => padding.top + chartHeight - (value / yMax) * chartHeight;

    const createLinePath = (key: 'leads' | 'appointments') => 
      data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(d[key])}`).join(' ');

    const createAreaPath = (key: 'leads' | 'appointments') => 
      `${createLinePath(key)} L ${xScale(data.length - 1)} ${yScale(0)} L ${xScale(0)} ${yScale(0)} Z`;

    const points = data.map((d, i) => ({
      x: xScale(i),
      yLeads: yScale(d.leads),
      yAppointments: yScale(d.appointments),
      data: d,
    }));

    return {
      xScale,
      yScale,
      yMax,
      linePathLeads: createLinePath('leads'),
      linePathAppointments: createLinePath('appointments'),
      areaPathLeads: createAreaPath('leads'),
      areaPathAppointments: createAreaPath('appointments'),
      points,
    };
  }, [data, chartWidth, chartHeight]);

  const handleMouseMove = (e: React.MouseEvent<SVGRectElement>) => {
    if (!points || points.length === 0) return;
    const svgRect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - svgRect.left;
    
    const closestPoint = points.reduce((prev, curr) => 
      Math.abs(curr.x - mouseX) < Math.abs(prev.x - mouseX) ? curr : prev
    );

    setTooltip({
      x: closestPoint.x,
      y: (closestPoint.yLeads + closestPoint.yAppointments) / 2,
      data: closestPoint.data,
    });
  };

  const handleMouseLeave = () => {
    setTooltip(null);
  };

  if (loading) {
    return (
      <Card className="p-6 animate-pulse">
        <div className="w-full h-[300px] bg-gray-700/50 rounded-md"></div>
      </Card>
    );
  }

  return (
    <Card className="p-4 sm:p-6">
      <div className="flex justify-end space-x-4 mb-4">
        <div className="flex items-center">
          <div className="w-3 h-3 rounded-full bg-blue-500 mr-2"></div>
          <span className="text-xs text-gray-400">Leads</span>
        </div>
        <div className="flex items-center">
          <div className="w-3 h-3 rounded-full bg-teal-400 mr-2"></div>
          <span className="text-xs text-gray-400">Appointments</span>
        </div>
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" aria-labelledby="chart-title" role="img">
          <title id="chart-title">Weekly performance chart showing leads and appointments.</title>
          {/* Grid lines */}
          {yScale && [0, 0.25, 0.5, 0.75, 1].map(tick => (
            <line
              key={tick}
              x1={padding.left}
              y1={yScale(tick * yMax)}
              x2={width - padding.right}
              y2={yScale(tick * yMax)}
              stroke="#2d3748"
              strokeWidth="1"
            />
          ))}

          {/* Area gradients */}
          <defs>
            <linearGradient id="areaGradientLeads" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="areaGradientAppointments" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2dd4bf" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#2dd4bf" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Area paths */}
          {areaPathLeads && <path d={areaPathLeads} fill="url(#areaGradientLeads)" />}
          {areaPathAppointments && <path d={areaPathAppointments} fill="url(#areaGradientAppointments)" />}

          {/* Line paths */}
          {linePathLeads && <path d={linePathLeads} fill="none" stroke="#3b82f6" strokeWidth="2.5" />}
          {linePathAppointments && <path d={linePathAppointments} fill="none" stroke="#2dd4bf" strokeWidth="2.5" />}

          {/* Points on hover */}
          {tooltip && (
            <g>
              <circle cx={tooltip.x} cy={yScale!(tooltip.data.leads)} r="5" fill="#3b82f6" stroke="#0a0a0a" strokeWidth="2" />
              <circle cx={tooltip.x} cy={yScale!(tooltip.data.appointments)} r="5" fill="#2dd4bf" stroke="#0a0a0a" strokeWidth="2" />
            </g>
          )}

          {/* Axes */}
          {xScale && data.map((d, i) => (
            <text key={i} x={xScale(i)} y={height - padding.bottom + 20} textAnchor="middle" fill="#9ca3af" fontSize="12">
              {d.day}
            </text>
          ))}
          {yScale && [0, 0.5, 1].map(tick => (
            <text key={tick} x={padding.left - 10} y={yScale(tick * yMax)} textAnchor="end" alignmentBaseline="middle" fill="#9ca3af" fontSize="12">
              {Math.round(tick * yMax)}
            </text>
          ))}

          {/* Tooltip */}
          {tooltip && (
            <g transform={`translate(${tooltip.x}, ${padding.top})`}>
              <line y1="0" y2={chartHeight} stroke="#4a5568" strokeWidth="1" strokeDasharray="3,3" />
              <foreignObject x={tooltip.x > width / 2 ? -140 : 10} y={tooltip.y - 40} width="130" height="80">
                <div className="bg-[#181818] border border-gray-700 rounded-lg p-2 shadow-2xl text-xs transition-opacity duration-200">
                  <div className="font-bold text-white mb-1 text-center">{tooltip.data.day}</div>
                  <div className="flex justify-between items-center">
                    <span className="text-blue-400 flex items-center"><div className="w-2 h-2 rounded-full bg-blue-500 mr-1.5"></div>Leads:</span>
                    <span className="font-semibold text-white">{tooltip.data.leads}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-teal-300 flex items-center"><div className="w-2 h-2 rounded-full bg-teal-400 mr-1.5"></div>Appts:</span>
                    <span className="font-semibold text-white">{tooltip.data.appointments}</span>
                  </div>
                </div>
              </foreignObject>
            </g>
          )}

          {/* Interaction layer */}
          <rect
            x={padding.left}
            y={padding.top}
            width={chartWidth}
            height={chartHeight}
            fill="transparent"
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          />
        </svg>
      </div>
    </Card>
  );
};

export default LeadsChart;