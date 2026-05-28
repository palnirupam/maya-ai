import React from 'react';
import { useAssistantStore, PendingToolRequest } from '../../store/assistantStore';
import { wsClient } from '../../services/websocket';

interface Props {
  request: PendingToolRequest;
}

export const ToolApprovalCard: React.FC<Props> = ({ request }) => {
  const removeToolRequest = useAssistantStore(state => state.removeToolRequest);

  const handleAction = (approved: boolean) => {
    // Send the resolution back to the backend
    wsClient.send('tool_resolution', {
      request_id: request.request_id,
      approved: approved
    });
    // Remove from UI queue
    removeToolRequest(request.request_id);
  };

  const riskColor = request.risk_level === 'high' ? 'bg-red-500/20 text-red-400 border-red-500' : 
                    request.risk_level === 'warning' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500' :
                    'bg-cyan-500/20 text-cyan-400 border-cyan-500';

  return (
    <div className={`p-4 my-2 border rounded-xl shadow-lg backdrop-blur-md ${riskColor}`}>
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-bold font-mono text-sm uppercase tracking-wider">⚡ Action Proposed: {request.tool_name}</h4>
        <span className="text-xs uppercase font-bold px-2 py-1 rounded bg-black/30">
          {request.risk_level}
        </span>
      </div>
      
      <div className="bg-black/40 p-3 rounded text-sm font-mono overflow-x-auto text-gray-300 whitespace-pre-wrap mb-4">
        {JSON.stringify(request.payload, null, 2)}
      </div>

      <div className="flex gap-3 mt-2">
        <button 
          onClick={() => handleAction(true)}
          className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-white font-bold py-2 px-4 rounded transition-colors"
        >
          Approve
        </button>
        <button 
          onClick={() => handleAction(false)}
          className="flex-1 bg-red-600 hover:bg-red-500 text-white font-bold py-2 px-4 rounded transition-colors"
        >
          Deny
        </button>
      </div>
    </div>
  );
};
