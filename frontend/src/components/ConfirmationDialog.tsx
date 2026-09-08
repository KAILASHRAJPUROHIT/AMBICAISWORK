import React from 'react';

interface ConfirmationDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  type?: 'NORMAL' | 'WARNING' | 'CRITICAL';
}

const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({ 
  isOpen, title, message, confirmLabel, onConfirm, onCancel, type = 'NORMAL' 
}) => {
  if (!isOpen) return null;

  const getThemeClasses = () => {
    switch(type) {
      case 'CRITICAL': return 'border-red-500 bg-red-50 text-red-700';
      case 'WARNING': return 'border-orange-500 bg-orange-50 text-orange-700';
      default: return 'border-gray-200 bg-white text-gray-900';
    }
  };

  const getBtnClasses = () => {
    switch(type) {
      case 'CRITICAL': return 'bg-red-600 hover:bg-red-700';
      case 'WARNING': return 'bg-orange-600 hover:bg-orange-700';
      default: return 'bg-black hover:bg-gray-800';
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-8 z-[100]">
      <div className={`max-w-md w-full rounded-3xl p-10 border-2 shadow-2xl ${getThemeClasses()}`}>
        <h3 className="text-2xl font-black uppercase tracking-tight mb-4">{title}</h3>
        <p className="text-sm font-medium mb-10 leading-relaxed opacity-80">{message}</p>
        
        <div className="flex space-x-4">
          <button 
            onClick={onCancel}
            className="flex-1 px-8 py-4 rounded-2xl font-black text-xs uppercase tracking-widest border border-current opacity-50 hover:opacity-100 transition-all"
          >
            Cancel
          </button>
          <button 
            onClick={onConfirm}
            className={`flex-1 px-8 py-4 rounded-2xl font-black text-xs uppercase tracking-widest text-white transition-all shadow-xl ${getBtnClasses()}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmationDialog;
