import React, { useEffect, useState } from "react";
import client from "../api/client";

import {
  Search,
  Edit,
  Trash2,
  Fingerprint,
  CreditCard,
  Camera,
  X,
  Save,
  Loader,
  RefreshCw,
  Shield,
  AlertCircle,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Mail,
  Phone,
  Briefcase,
  ArrowLeft,
  Filter,
  Eye,
  Radio,
  ScanLine,
  User,
  Calendar,
  Droplet,
  MapPin,
  Users,
  Heart
} from "lucide-react";

export default function EmployeesListPage() {
  const [list, setList] = useState([]);
  const [offices, setOffices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedOffice, setSelectedOffice] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(10);
  
  // Edit form state
  const [showEditForm, setShowEditForm] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [editForm, setEditForm] = useState({
    emp_id: "",
    name: "",
    email: "",
    phone: "",
    address: "",
    gender: "",
    blood_group: "",
    date_of_birth: "",
    position: "",
    joined_date: "",
    office_id: "",
    photo: ""
  });
  
  // View modal state
  const [showViewModal, setShowViewModal] = useState(false);
  const [viewingEmployee, setViewingEmployee] = useState(null);
  
  // Delete confirmation
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [employeeToDelete, setEmployeeToDelete] = useState(null);
  
  // Biometric enrollment during edit
  const [enrollingBio, setEnrollingBio] = useState({
    type: null,
    index: null,
    waiting: false,
    startTime: null
  });

  // Load data
  const loadEmployees = async () => {
    setLoading(true);
    try {
      const res = await client.get("/employees");
      console.log("Loaded employees:", res.data); // Debug log
      setList(res.data);
      setError("");
    } catch (err) {
      setError("Failed to load employees");
    }
    setLoading(false);
  };

  const loadOffices = async () => {
    try {
      const res = await client.get("/offices");
      setOffices(res.data);
    } catch (err) {
      console.error("Failed to load offices:", err);
    }
  };

  useEffect(() => {
    loadEmployees();
    loadOffices();
  }, []);

  // Check hardware response during enrollment
  useEffect(() => {
    if (!enrollingBio.waiting) return;
    
    let checkCount = 0;
    const maxChecks = 30;
    
    const interval = setInterval(async () => {
      checkCount++;
      
      try {
        const res = await client.get("/hardware/command");
        console.log("Hardware state:", res.data);
        
        if (res.data.command === 0) {
          if (enrollingBio.type === 'face' && enrollingBio.index) {
            try {
              const previewRes = await client.get(`/hardware/face-preview/${enrollingBio.index}?emp_id=${editForm.emp_id}`);
              
              if (previewRes.data.image) {
                const base64Image = previewRes.data.image.startsWith('data:image') 
                  ? previewRes.data.image 
                  : `data:image/jpeg;base64,${previewRes.data.image}`;
                
                console.log("Face captured:", base64Image.substring(0, 50) + "...");
              }
              
              setSuccess(`Face ${enrollingBio.index} captured successfully!`);
            } catch (err) {
              console.error("Error fetching face preview:", err);
              setSuccess(`Face ${enrollingBio.index} captured!`);
            }
          } 
          else if (enrollingBio.type === 'finger' && enrollingBio.index) {
            setSuccess(`Fingerprint ${enrollingBio.index} captured successfully!`);
          } 
          else if (enrollingBio.type === 'rfid') {
            setSuccess(`RFID captured successfully!`);
          }
          
          loadEmployees();
          setEnrollingBio({ type: null, index: null, waiting: false, startTime: null });
          
        } else if (checkCount >= maxChecks) {
          setEnrollingBio({ type: null, index: null, waiting: false, startTime: null });
          setError(`${getBioType(enrollingBio.type)} capture timeout - please try again`);
          setTimeout(() => setError(""), 3000);
        }
      } catch (err) {
        console.error("Error checking hardware:", err);
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [enrollingBio.waiting, enrollingBio.type, enrollingBio.index, editForm.emp_id]);

  const captureBiometric = async (type, index = null) => {
    if (!editForm.emp_id) {
      setError("Employee ID not found");
      setTimeout(() => setError(""), 3000);
      return;
    }

    try {
      await client.post("/hardware/reset");
      
      let command = 1;
      if (type === 'finger') command = 2;
      if (type === 'face') command = 3;
      
      await client.post("/hardware/command", {
        emp_id: editForm.emp_id,
        command: command,
        index: index
      });
      
      setEnrollingBio({ 
        type, 
        index, 
        waiting: true,
        startTime: Date.now()
      });
      
      setSuccess(`Waiting for ${getBioType(type)} ${index || ''} from Raspberry Pi...`);
      
    } catch (err) {
      setError("Failed to send command to hardware");
      setTimeout(() => setError(""), 3000);
    }
  };

  const openEditForm = (emp) => {
    setEditingEmployee(emp);
    setEditForm({
      emp_id: emp.emp_id,
      name: emp.name,
      email: emp.email || "",
      phone: emp.phone || "",
      address: emp.address || "",
      gender: emp.gender || "",
      blood_group: emp.blood_group || "",
      date_of_birth: emp.date_of_birth || "",
      position: emp.position,
      joined_date: emp.joined_date,
      office_id: emp.office_id,
      photo: emp.photo || ""
    });
    setShowEditForm(true);
    setEnrollingBio({ type: null, index: null, waiting: false, startTime: null });
    setTimeout(() => {
      document.getElementById('edit-form')?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  const closeEditForm = () => {
    setShowEditForm(false);
    setEditingEmployee(null);
    setEnrollingBio({ type: null, index: null, waiting: false, startTime: null });
  };

  const openViewModal = (emp) => {
    setViewingEmployee(emp);
    setShowViewModal(true);
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      await client.put(`/employees/${editForm.emp_id}`, {
        ...editForm,
        office_id: Number(editForm.office_id)
      });
      
      setSuccess("Employee updated successfully!");
      closeEditForm();
      loadEmployees();
      setTimeout(() => setSuccess(""), 3000);
    } catch (err) {
      setError("Failed to update employee");
    } finally {
      setLoading(false);
    }
  };

  const confirmDelete = (emp) => {
    setEmployeeToDelete(emp);
    setShowDeleteModal(true);
  };

  const handleDelete = async () => {
    if (!employeeToDelete) return;
    
    try {
      await client.delete(`/employees/${employeeToDelete.emp_id}`);
      setSuccess("Employee deleted successfully!");
      setShowDeleteModal(false);
      setEmployeeToDelete(null);
      loadEmployees();
      setTimeout(() => setSuccess(""), 3000);
    } catch (err) {
      setError("Failed to delete employee");
    }
  };

  const getBioType = (type) => {
    const types = { rfid: 'RFID', finger: 'Fingerprint', face: 'Face' };
    return types[type] || type;
  };

  const getOfficeName = (officeId) => {
    const office = offices.find(o => o.id === officeId);
    return office?.name || "N/A";
  };

  const getInitials = (name) => {
    return name?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) || 'EM';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    }).replace(/\//g, '-');
  };

  const filteredEmployees = list.filter(emp => {
    const matchesSearch = 
      emp.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      emp.emp_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      emp.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      emp.phone?.includes(searchTerm) ||
      emp.position?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      emp.gender?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      emp.blood_group?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      emp.address?.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesOffice = selectedOffice === "all" || emp.office_id === Number(selectedOffice);
    
    return matchesSearch && matchesOffice;
  });

  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentItems = filteredEmployees.slice(indexOfFirstItem, indexOfLastItem);
  const totalPages = Math.ceil(filteredEmployees.length / itemsPerPage);

  const hasRFID = (emp) => emp.rfid_uid && emp.rfid_uid !== '';
  const hasFingerprint = (emp) => emp.fingerprint_1 || emp.fingerprint_2 || emp.fingerprint_3 || emp.fingerprint_4;
  const hasFace = (emp) => emp.face_image_1 || emp.face_image_2 || emp.face_image_3 || 
                         emp.face_image_4 || emp.face_image_5;

  const getFingerprintCount = (emp) => {
    return [emp.fingerprint_1, emp.fingerprint_2, emp.fingerprint_3, emp.fingerprint_4].filter(Boolean).length;
  };

  const getFaceCount = (emp) => {
    return [emp.face_image_1, emp.face_image_2, emp.face_image_3, emp.face_image_4, emp.face_image_5].filter(Boolean).length;
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <div className="sticky top-0 z-10 shadow-sm" style={{ backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-primary)' }}>
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button 
                onClick={() => window.history.back()}
                className="p-2 hover:bg-black/5 rounded-lg transition-colors"
              >
                <ArrowLeft className="h-5 w-5" style={{ color: 'var(--text-secondary)' }} />
              </button>
              <div className="flex items-center gap-3">
                <Shield className="h-8 w-8" style={{ color: 'var(--accent)' }} />
                <div>
                  <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Employees</h1>
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Manage employees and biometrics</p>
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={loadEmployees}
                className="p-2 border rounded-lg hover:bg-black/5 transition-colors"
                style={{ borderColor: 'var(--border-primary)' }}
                title="Refresh"
              >
                <RefreshCw className="h-4 w-4" style={{ color: 'var(--text-secondary)' }} />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="px-6 py-4">
        {/* Status Messages */}
        {success && (
          <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
            <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />
            <p className="text-green-700 text-sm">{success}</p>
          </div>
        )}

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}

        {/* Search and Filter */}
        <div className="mb-4 flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4" style={{ color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search by name, ID, email, position, gender, blood group, address..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input-field pl-9"
            />
          </div>
          <select
            value={selectedOffice}
            onChange={(e) => setSelectedOffice(e.target.value)}
            className="input-field w-auto"
          >
            <option value="all">All Offices</option>
            {offices.map(office => (
              <option key={office.id} value={office.id}>{office.name}</option>
            ))}
          </select>
          <button
            onClick={() => {
              setSearchTerm("");
              setSelectedOffice("all");
            }}
            className="btn-secondary"
          >
            Clear
          </button>
        </div>

        {/* Employees Table */}
        {loading ? (
          <div className="flex justify-center items-center h-64">
            <Loader className="h-8 w-8 animate-spin" style={{ color: 'var(--accent)' }} />
          </div>
        ) : (
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="table-header">
                  <tr>
                    <th className="px-6 py-3 text-left">Employee</th>
                    <th className="px-6 py-3 text-left">Contact</th>
                    <th className="px-6 py-3 text-left">Personal Info</th>
                    <th className="px-6 py-3 text-left">Position</th>
                    <th className="px-6 py-3 text-left">Biometrics</th>
                  
                    <th className="px-6 py-3 text-left">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {currentItems.map((emp) => (
                    <tr key={emp.id} className="table-row">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center text-white font-medium text-sm">
                            {emp.photo ? (
                              <img src={emp.photo} alt={emp.name} className="h-10 w-10 rounded-full object-cover" />
                            ) : (
                              getInitials(emp.name)
                            )}
                          </div>
                          <div>
                            <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{emp.name}</div>
                            <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>EmpID: {emp.emp_id}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm space-y-1">
                          <div className="flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                            <Mail className="h-3 w-3" />
                            <span className="truncate max-w-[150px]" title={emp.email}>{emp.email || '-'}</span>
                          </div>
                          <div className="flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                            <Phone className="h-3 w-3" />
                            <span>{emp.phone || '-'}</span>
                          </div>
                          <div className="flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                            <MapPin className="h-3 w-3" />
                            <span className="truncate max-w-[150px]" title={emp.address}>{emp.address || '-'}</span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm space-y-1">
                          <div className="flex items-center gap-1">
                            <Users className="h-3 w-3" style={{ color: 'var(--text-muted)' }} />
                            <span className="capitalize">{emp.gender || 'Not specified'}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <Heart className="h-3 w-3 text-red-400" />
                            <span className="font-mono">{emp.blood_group || 'N/A'}</span>
                          </div>
                         
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div>
                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{emp.position}</div>
                          <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                            <span className="px-2 py-1 rounded-full inline-block" style={{ backgroundColor: 'var(--accent-light)', color: 'var(--accent)' }}>
                              {getOfficeName(emp.office_id)}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-col gap-1">
                          {hasRFID(emp) && (
                            <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded-full flex items-center gap-1 w-fit">
                              <CreditCard className="h-3 w-3" />
                              RFID: {emp.rfid_uid}
                            </span>
                          )}
                          {hasFingerprint(emp) && (
                            <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full flex items-center gap-1 w-fit">
                              <Fingerprint className="h-3 w-3" />
                              FP: {getFingerprintCount(emp)}/4
                            </span>
                          )}
                          {hasFace(emp) && (
                            <span className="text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded-full flex items-center gap-1 w-fit">
                              <Camera className="h-3 w-3" />
                              Face: {getFaceCount(emp)}/5
                            </span>
                          )}
                          {!hasRFID(emp) && !hasFingerprint(emp) && !hasFace(emp) && (
                            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>No biometrics</span>
                          )}
                        </div>
                      </td>
                     
                      <td className="px-6 py-4">
                        <div className="flex gap-2">
                          <button
                            onClick={() => openViewModal(emp)}
                            className="p-1.5 rounded-lg transition-colors"
                            style={{ color: 'var(--accent)' }}
                            title="View"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => openEditForm(emp)}
                            className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                            title="Edit"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => confirmDelete(emp)}
                            className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}

                  {currentItems.length === 0 && (
                    <tr>
                      <td colSpan="7" className="px-6 py-12 text-center" style={{ color: 'var(--text-secondary)' }}>
                        No employees found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {filteredEmployees.length > 0 && (
              <div className="px-6 py-4 border-t flex items-center justify-between" style={{ borderColor: 'var(--border-primary)' }}>
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  Showing {indexOfFirstItem + 1} to {Math.min(indexOfLastItem, filteredEmployees.length)} of {filteredEmployees.length}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="p-2 border rounded-lg disabled:opacity-50 hover:bg-black/5 transition-colors"
                    style={{ borderColor: 'var(--border-primary)' }}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: 'var(--accent)', color: 'white' }}>
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="p-2 border rounded-lg disabled:opacity-50 hover:bg-black/5 transition-colors"
                    style={{ borderColor: 'var(--border-primary)' }}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Inline Edit Form */}
        {showEditForm && (
          <div id="edit-form" className="mt-6 card overflow-hidden">
            <div className="bg-gradient-to-r from-orange-500 to-amber-500 px-6 py-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Edit className="h-5 w-5" />
                  Edit Employee: {editingEmployee?.name}
                </h2>
                <button 
                  onClick={closeEditForm}
                  className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
                  title="Close"
                >
                  <X className="h-5 w-5 text-white" />
                </button>
              </div>
            </div>

            <form onSubmit={handleEditSubmit} className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Employee ID</label>
                  <input
                    value={editForm.emp_id}
                    disabled
                    className="w-full input-field"
                    style={{ backgroundColor: 'var(--bg-tertiary)' }}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Full Name *</label>
                  <input
                    required
                    value={editForm.name}
                    onChange={e => setEditForm({...editForm, name: e.target.value})}
                    className="w-full input-field"
                    placeholder="Enter full name"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Email</label>
                  <input
                    type="email"
                    value={editForm.email}
                    onChange={e => setEditForm({...editForm, email: e.target.value})}
                    className="w-full input-field"
                    placeholder="email@example.com"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Phone</label>
                  <input
                    value={editForm.phone}
                    onChange={e => setEditForm({...editForm, phone: e.target.value})}
                    className="w-full input-field"
                    placeholder="+91 9876543210"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Address</label>
                  <input
                    value={editForm.address}
                    onChange={e => setEditForm({...editForm, address: e.target.value})}
                    className="w-full input-field"
                    placeholder="Enter address"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Gender</label>
                  <select
                    value={editForm.gender}
                    onChange={e => setEditForm({...editForm, gender: e.target.value})}
                    className="w-full input-field"
                  >
                    <option value="">Select Gender</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Blood Group</label>
                  <input
                    value={editForm.blood_group}
                    onChange={e => setEditForm({...editForm, blood_group: e.target.value})}
                    className="w-full input-field"
                    placeholder="O+"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Date of Birth</label>
                  <input
                    type="date"
                    value={editForm.date_of_birth}
                    onChange={e => setEditForm({...editForm, date_of_birth: e.target.value})}
                    className="w-full input-field"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Joined Date *</label>
                  <input
                    type="date"
                    required
                    value={editForm.joined_date}
                    onChange={e => setEditForm({...editForm, joined_date: e.target.value})}
                    className="w-full input-field"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Position *</label>
                  <input
                    required
                    value={editForm.position}
                    onChange={e => setEditForm({...editForm, position: e.target.value})}
                    className="w-full input-field"
                    placeholder="Software Engineer"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>Office *</label>
                  <select
                    required
                    value={editForm.office_id}
                    onChange={e => setEditForm({...editForm, office_id: e.target.value})}
                    className="w-full input-field"
                  >
                    <option value="">Select Office</option>
                    {offices.map(o => (
                      <option key={o.id} value={o.id}>{o.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Biometric Enrollment Section */}
              <div className="mt-8 pt-6 border-t" style={{ borderColor: 'var(--border-primary)' }}>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                  <Fingerprint className="h-5 w-5" style={{ color: 'var(--accent)' }} />
                  Capture New Biometrics
                </h3>
                
                <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
                  Click buttons to capture new biometric data. This will update the employee's records.
                </p>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* RFID */}
                  <div className="space-y-3">
                    <label className="block text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>RFID Card</label>
                    <button
                      type="button"
                      onClick={() => captureBiometric('rfid')}
                      disabled={enrollingBio.waiting}
                      className={`w-full px-4 py-3 rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50 ${
                        enrollingBio.waiting && enrollingBio.type === 'rfid'
                          ? 'animate-pulse'
                          : ''
                      }`}
                      style={{
                        backgroundColor: 'var(--accent-light)',
                        color: 'var(--accent)',
                        borderColor: 'var(--accent)',
                        borderWidth: '1px'
                      }}
                    >
                      {enrollingBio.waiting && enrollingBio.type === 'rfid' ? (
                        <>
                          <Loader className="h-4 w-4 animate-spin" />
                          Waiting...
                        </>
                      ) : (
                        <>
                          <CreditCard className="h-4 w-4" />
                          Capture RFID
                        </>
                      )}
                    </button>
                  </div>

                  {/* Fingerprint */}
                  <div className="space-y-3">
                    <label className="block text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Fingerprints</label>
                    <div className="grid grid-cols-2 gap-2">
                      {[1, 2, 3, 4].map(i => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => captureBiometric('finger', i)}
                          disabled={enrollingBio.waiting}
                          className={`px-3 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                            enrollingBio.waiting && enrollingBio.type === 'finger' && enrollingBio.index === i
                              ? 'animate-pulse'
                              : ''
                          }`}
                          style={{
                            backgroundColor: enrollingBio.waiting && enrollingBio.type === 'finger' && enrollingBio.index === i
                              ? 'var(--accent-light)'
                              : 'var(--bg-tertiary)',
                            color: enrollingBio.waiting && enrollingBio.type === 'finger' && enrollingBio.index === i
                              ? 'var(--accent)'
                              : 'var(--text-secondary)'
                          }}
                        >
                          {enrollingBio.waiting && enrollingBio.type === 'finger' && enrollingBio.index === i ? (
                            <Loader className="h-4 w-4 animate-spin mx-auto" />
                          ) : (
                            `Finger ${i}`
                          )}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Face */}
                  <div className="space-y-3">
                    <label className="block text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Face Recognition</label>
                    <div className="grid grid-cols-3 gap-2">
                      {[1, 2, 3, 4, 5].map(i => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => captureBiometric('face', i)}
                          disabled={enrollingBio.waiting}
                          className={`px-3 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                            enrollingBio.waiting && enrollingBio.type === 'face' && enrollingBio.index === i
                              ? 'animate-pulse'
                              : ''
                          }`}
                          style={{
                            backgroundColor: enrollingBio.waiting && enrollingBio.type === 'face' && enrollingBio.index === i
                              ? 'var(--accent-light)'
                              : 'var(--bg-tertiary)',
                            color: enrollingBio.waiting && enrollingBio.type === 'face' && enrollingBio.index === i
                              ? 'var(--accent)'
                              : 'var(--text-secondary)'
                          }}
                        >
                          {enrollingBio.waiting && enrollingBio.type === 'face' && enrollingBio.index === i ? (
                            <Loader className="h-4 w-4 animate-spin mx-auto" />
                          ) : (
                            i
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Waiting Hint */}
                {enrollingBio.waiting && (
                  <div className="mt-4 p-3 text-sm rounded-lg text-center animate-pulse" style={{ backgroundColor: 'var(--accent-light)', color: 'var(--accent)' }}>
                    ⏳ Waiting for {getBioType(enrollingBio.type)} {enrollingBio.index || ''}...
                    Please perform the action on the hardware.
                  </div>
                )}
              </div>

              {/* Form Actions */}
              <div className="mt-8 pt-6 border-t flex justify-end gap-3" style={{ borderColor: 'var(--border-primary)' }}>
                <button
                  type="button"
                  onClick={closeEditForm}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary disabled:opacity-50"
                >
                  {loading ? (
                    <>
                      <Loader className="h-4 w-4 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4" />
                      Update Employee
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      {/* View Employee Modal */}
      {showViewModal && viewingEmployee && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="card shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 px-6 py-4 flex justify-between items-center" style={{ backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-primary)' }}>
              <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Employee Details</h2>
              <button 
                onClick={() => setShowViewModal(false)} 
                className="p-2 hover:bg-black/5 rounded-lg"
              >
                <X className="h-5 w-5" style={{ color: 'var(--text-secondary)' }} />
              </button>
            </div>

            <div className="p-6">
              <div className="flex items-center gap-4 mb-6">
                <div className="h-16 w-16 rounded-full bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center text-white font-bold text-xl">
                  {viewingEmployee.photo ? (
                    <img src={viewingEmployee.photo} alt={viewingEmployee.name} className="h-16 w-16 rounded-full object-cover" />
                  ) : (
                    getInitials(viewingEmployee.name)
                  )}
                </div>
                <div>
                  <h3 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{viewingEmployee.name}</h3>
                  <p style={{ color: 'var(--text-secondary)' }}>ID: {viewingEmployee.emp_id}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Email</label>
                  <p className="text-sm font-medium">{viewingEmployee.email || '-'}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Phone</label>
                  <p className="text-sm font-medium">{viewingEmployee.phone || '-'}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Address</label>
                  <p className="text-sm font-medium">{viewingEmployee.address || '-'}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Gender</label>
                  <p className="text-sm font-medium">{viewingEmployee.gender || '-'}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Blood Group</label>
                  <p className="text-sm font-medium">{viewingEmployee.blood_group || '-'}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Date of Birth</label>
                  <p className="text-sm font-medium">{formatDate(viewingEmployee.date_of_birth)}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Position</label>
                  <p className="text-sm font-medium">{viewingEmployee.position}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Office</label>
                  <p className="text-sm font-medium">{getOfficeName(viewingEmployee.office_id)}</p>
                </div>
                <div>
                  <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Joined Date</label>
                  <p className="text-sm font-medium">{formatDate(viewingEmployee.joined_date)}</p>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t" style={{ borderColor: 'var(--border-primary)' }}>
                <h4 className="font-medium mb-2">Biometrics</h4>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <CreditCard className={`h-4 w-4 ${hasRFID(viewingEmployee) ? 'text-purple-600' : ''}`} style={{ color: hasRFID(viewingEmployee) ? undefined : 'var(--text-muted)' }} />
                    <span className="text-sm">{hasRFID(viewingEmployee) ? `RFID: ${viewingEmployee.rfid_uid}` : 'No RFID'}</span>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <Fingerprint className={`h-4 w-4 ${hasFingerprint(viewingEmployee) ? 'text-green-600' : ''}`} style={{ color: hasFingerprint(viewingEmployee) ? undefined : 'var(--text-muted)' }} />
                    <span className="text-sm">
                      {hasFingerprint(viewingEmployee) 
                        ? `Fingerprints: ${getFingerprintCount(viewingEmployee)}/4` 
                        : 'No Fingerprints'}
                    </span>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <Camera className={`h-4 w-4 ${hasFace(viewingEmployee) ? 'text-orange-600' : ''}`} style={{ color: hasFace(viewingEmployee) ? undefined : 'var(--text-muted)' }} />
                    <span className="text-sm">
                      {hasFace(viewingEmployee) 
                        ? `Face Images: ${getFaceCount(viewingEmployee)}/5` 
                        : 'No Face Images'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => setShowViewModal(false)}
                  className="btn-primary"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && employeeToDelete && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="card shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 text-red-600 mb-4">
              <AlertCircle className="h-6 w-6" />
              <h3 className="text-lg font-semibold">Confirm Delete</h3>
            </div>
            <p className="mb-6" style={{ color: 'var(--text-secondary)' }}>
              Are you sure you want to delete <span className="font-semibold">{employeeToDelete.name}</span>? 
              This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
