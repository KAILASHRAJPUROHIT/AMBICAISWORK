import React, { useState } from 'react';
import { getHeaders } from '../api/client';

interface UserManagementDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const UserManagementDialog: React.FC<UserManagementDialogProps> = ({ isOpen, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    employee_id: '',
    name: '',
    email: '',
    role: 'ACCOUNTANT',
    password: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${window.location.origin}/api/admin/users`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(formData)
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to create user');
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-8 z-[100]">
      <div className="bg-white max-w-lg w-full rounded-3xl p-10 shadow-2xl border border-gray-100">
        <h3 className="text-2xl font-black uppercase mb-6 tracking-tight">Create New User</h3>
        
        {error && <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-xs font-bold uppercase">{error}</div>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
             <div className="space-y-2">
                <label className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Employee ID</label>
                <input 
                    type="text" 
                    className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                    value={formData.employee_id}
                    onChange={e => setFormData({...formData, employee_id: e.target.value.toUpperCase()})}
                    required
                />
             </div>
             <div className="space-y-2">
                <label className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Role</label>
                <select 
                    className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-black uppercase text-xs"
                    value={formData.role}
                    onChange={e => setFormData({...formData, role: e.target.value})}
                >
                    <option value="ACCOUNTANT">Accountant</option>
                    <option value="OWNER">Owner</option>
                    <option value="ADMIN">Admin</option>
                    <option value="STAFF">Staff</option>
                </select>
             </div>
          </div>

          <div className="space-y-2">
             <label className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Full Name</label>
             <input 
                type="text" 
                className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value})}
                required
             />
          </div>

          <div className="space-y-2">
             <label className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Email Address</label>
             <input 
                type="email" 
                className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                value={formData.email}
                onChange={e => setFormData({...formData, email: e.target.value})}
                required
             />
          </div>

          <div className="space-y-2">
             <label className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Temporary Password</label>
             <input 
                type="password" 
                className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                value={formData.password}
                onChange={e => setFormData({...formData, password: e.target.value})}
                required
             />
          </div>

          <div className="pt-6 flex space-x-4">
             <button type="button" onClick={onClose} className="flex-1 p-4 rounded-2xl font-black uppercase text-xs tracking-widest text-gray-400 hover:bg-gray-50">Cancel</button>
             <button type="submit" disabled={loading} className="flex-1 p-4 rounded-2xl bg-black text-white font-black uppercase text-xs tracking-widest shadow-xl shadow-black/10 hover:bg-gray-900 transition-all">
                {loading ? 'Creating...' : 'Create User'}
             </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UserManagementDialog;
