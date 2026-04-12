import React from 'react';

export const OrdersActivityIndicator: React.FC = () => (
  <span className="flex space-x-0.5 mr-1.5">
    <span className="w-0.5 h-2 bg-current animate-[bounce_1s_infinite_0ms]" />
    <span className="w-0.5 h-2 bg-current animate-[bounce_1s_infinite_200ms]" />
    <span className="w-0.5 h-2 bg-current animate-[bounce_1s_infinite_400ms]" />
  </span>
);
