import React, { useState, useEffect, useMemo, useCallback } from 'react';

// Use environment variable for API URL, fallback to localhost for development
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Memoized EventRow component to prevent unnecessary re-renders
const EventRow = React.memo(({ 
  event, 
  onActionSelect, 
  normalizeLocation, 
  formatDate, 
  formatActionTime, 
  getActionColor, 
  getTypeColor 
}) => {
  const handleActionChange = useCallback((e) => {
    onActionSelect(String(event.id), event.type, e.target.value);
  }, [event.id, event.type, onActionSelect]);

  return (
    <tr key={String(event.id)} className="hover:bg-gray-50">
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="text-sm font-medium text-gray-900">{event.title}</div>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getTypeColor(event.type)}`}>
          {event.type}
        </span>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
        {normalizeLocation(event.location)}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
        {formatDate(event.start_date)}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
        {formatDate(event.end_date)}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
        {event.url ? (
          <a 
            href={event.url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 hover:underline"
          >
            Visit
          </a>
        ) : 'N/A'}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
        {event.last_action ? (
          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getActionColor(event.last_action)}`}>
            {event.last_action}
          </span>
        ) : '—'}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
        {event.action_time ? formatActionTime(event.action_time) : '—'}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
        <select
          defaultValue=""
          onChange={handleActionChange}
          className="block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
        >
          <option value="" disabled>Choose Action</option>
          <option value="reached_out">Mark as Reached Out</option>
          <option value="archive">Archive</option>
        </select>
      </td>
    </tr>
  );
});

const EventsPage = () => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filter states
  const [typeFilter, setTypeFilter] = useState('');
  const [locationFilter, setLocationFilter] = useState('');

  // Memoized utility functions to prevent recreation on every render
  const normalizeLocation = useCallback((location) => {
    if (!location) return 'N/A';
    
    // Replace Virtual/Online with Remote
    if (location.toLowerCase().includes('virtual') || location.toLowerCase().includes('online')) {
      return 'Remote';
    }
    
    // Convert all-uppercase to proper case
    if (location === location.toUpperCase() && location.length > 2) {
      return location.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
    }
    
    return location;
  }, []);

  const formatDate = useCallback((dateString) => {
    if (!dateString) return '—';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return 'TBD';
    }
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  }, []);

  const formatActionTime = useCallback((timestamp) => {
    if (!timestamp) return '—';
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return '—';
    
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  }, []);

  const getActionColor = useCallback((action) => {
    switch (action) {
      case 'archive': return 'bg-red-100 text-red-800';
      case 'reached_out': return 'bg-green-100 text-green-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  }, []);

  const getTypeColor = useCallback((type) => {
    switch (type) {
      case 'hackathon': return 'bg-blue-100 text-blue-800';
      case 'conference': return 'bg-purple-100 text-purple-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  }, []);

  // Optimized handleActionSelect with useCallback
  const handleActionSelect = useCallback(async (eventId, eventType, action) => {
    if (!action) return;
    console.log(`Attempting action: ${action} for event ${eventId} (${eventType})`);
    
    try {
      const res = await fetch(`${API_BASE_URL}/event-action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_id: eventId,
          event_type: eventType,
          action,
        }),
      });
      
      if (res.ok) {
        console.log("Action recorded successfully, reloading...");
        fetchEvents(); // Re-fetch all events to update UI
      } else {
        const errorData = await res.json();
        console.error("Failed to record action:", res.status, errorData);
        alert(`Failed to record action: ${errorData.detail || res.statusText}`);
      }
    } catch (error) {
      console.error("Action submission failed:", error);
      alert("Error submitting action.");
    }
  }, []);

  // PERFORMANCE OPTIMIZED: Single API call that includes action data
  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${API_BASE_URL}/events`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      let data = await response.json();

      // Ensure event.id is a string for consistent key usage
      data = data.map(event => ({ ...event, id: String(event.id) }));
      
      setEvents(data);
      
      // Check performance headers
      const processTime = response.headers.get('X-Process-Time');
      if (processTime) {
        console.log(`✅ API response time: ${(parseFloat(processTime) * 1000).toFixed(0)}ms`);
      }
      
    } catch (err) {
      console.error('Error fetching events:', err);
      setError(`Failed to fetch events: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  // Memoized filtered and sorted events
  const filteredAndSortedEvents = useMemo(() => {
    let filtered = events;

    if (typeFilter) {
      filtered = filtered.filter(event => event.type === typeFilter);
    }

    if (locationFilter) {
      filtered = filtered.filter(event => 
        event.location && normalizeLocation(event.location).toLowerCase().includes(locationFilter.toLowerCase())
      );
    }

    // Helper function to get a sortable Date object
    const getSortableDate = (dateString) => {
      if (!dateString) {
        return new Date('1900-01-01');
      }
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return new Date('1900-01-01');
      }
      return date;
    };

    // Sort by date descending
    return [...filtered].sort((a, b) => {
      const dateA = getSortableDate(a.start_date);
      const dateB = getSortableDate(b.start_date);
      return dateB.getTime() - dateA.getTime();
    });
  }, [events, typeFilter, locationFilter, normalizeLocation]);

  // Memoized unique types for filter dropdown
  const uniqueTypes = useMemo(() => {
    return [...new Set(events.map(event => event.type))];
  }, [events]);

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading events...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center p-8 bg-white rounded-lg shadow-md max-w-md">
          <div className="text-red-500 text-6xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold text-gray-800 mb-2">Error Loading Events</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <button 
            onClick={fetchEvents}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Events Dashboard</h1>
              <p className="mt-1 text-gray-500">
                Hackathons and conferences from your database 
                <span className="text-green-600 font-medium"> • Optimized Performance</span>
              </p>
            </div>
            <button 
              onClick={fetchEvents}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Filters</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Type Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Type</label>
              <select 
                value={typeFilter} 
                onChange={(e) => setTypeFilter(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All Types</option>
                {uniqueTypes.map(type => (
                  <option key={type} value={type}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            {/* Location Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Location</label>
              <input
                type="text"
                placeholder="Search by location..."
                value={locationFilter}
                onChange={(e) => setLocationFilter(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* Events Table */}
        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-medium text-gray-900">
              Events ({filteredAndSortedEvents.length})
              <span className="text-sm text-green-600 font-normal ml-2">
                ⚡ Single query optimization
              </span>
            </h2>
          </div>
          
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Location
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Start Date
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    End Date
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    URL
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Action
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Action Time
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Manage
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredAndSortedEvents.map((event) => (
                  <EventRow
                    key={String(event.id)}
                    event={event}
                    onActionSelect={handleActionSelect}
                    normalizeLocation={normalizeLocation}
                    formatDate={formatDate}
                    formatActionTime={formatActionTime}
                    getActionColor={getActionColor}
                    getTypeColor={getTypeColor}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {filteredAndSortedEvents.length === 0 && (
            <div className="text-center py-12">
              <div className="text-gray-400 text-6xl mb-4">📅</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No events found</h3>
              <p className="text-gray-500">Try adjusting your filters or refresh the data.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EventsPage; 