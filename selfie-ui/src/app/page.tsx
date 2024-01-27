"use client"

import React, { useState, useEffect } from 'react';

const SelfieManager = () => {
  const [dataSources, setDataSources] = useState([]);
  const [documents, setDocuments] = useState({});
  const [selectedDocuments, setSelectedDocuments] = useState(new Set());
  const [isChat, setIsChat] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log("USE EFFECT")
    fetchDataSources();
  }, []);

  const fetchDataSources = async () => {
    try {
      console.log("FETCHING DATA SOURCES")
      const response = await fetch('http://localhost:8181/v1/data-sources');
      const data = await response.json();
      setDataSources(data);
      data.forEach(dataSource => fetchDocuments(dataSource.id));
    } catch (error) {
      console.error('Error fetching data sources:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDocuments = async (sourceId) => {
    try {
      const response = await fetch(`http://localhost:8181/v1/documents?source_id=${sourceId}`);
      const docs = await response.json();
      setDocuments(prevDocs => ({ ...prevDocs, [sourceId]: docs }));
    } catch (error) {
      console.error('Error fetching documents:', error);
    }
  };

  const handleScan = async (sourceId) => {
    await fetch(`http://localhost:8181/v1/data-sources/${sourceId}/scan`, { method: 'POST' });
    fetchDocuments(sourceId);
  };

  const handleIndex = async (sourceId) => {
    await fetch(`http://localhost:8181/v1/data-sources/${sourceId}/index`, { method: 'POST' });
  };

  const handleIndexSelectedDocuments = async () => {
    const documentIds = Array.from(selectedDocuments);
    await fetch('http://localhost:8181/v1/documents/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_ids: documentIds, is_chat: isChat })
    });
    setSelectedDocuments(new Set()); // Optionally reset selection after indexing
  };

  const toggleDocumentSelection = (docId) => {
    setSelectedDocuments(prev => new Set(prev.has(docId) ? prev.delete(docId) && prev : prev.add(docId)));
  };

  if (loading) return <div>Loading data sources...</div>;

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-4xl font-bold mb-4">Data Source Manager</h1>
      {dataSources.map((dataSource) => (
        <div key={dataSource.id} className="mb-6">
          <div className="flex justify-between items-center mb-2">
            <h2 className="text-xl font-semibold">{dataSource.name}</h2>
            <div>
              <button className="btn btn-primary mr-2" onClick={() => handleScan(dataSource.id)}>Scan</button>
              <button className="btn btn-secondary" onClick={() => handleIndex(dataSource.id)}>Index</button>
            </div>
          </div>
          <table className="table w-full">
            <thead>
            <tr>
              <th>Select</th>
              <th>Document ID</th>
              <th>Metadata</th>
            </tr>
            </thead>
            <tbody>
            {documents[dataSource.id]?.map(doc => (
              <tr key={doc.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedDocuments.has(doc.id)}
                    onChange={() => toggleDocumentSelection(doc.id)}
                    className="checkbox checkbox-primary"
                  />
                </td>
                <td>{doc.id}</td>
                <td>{JSON.stringify(doc.metadata)}</td>
              </tr>
            ))}
            </tbody>
          </table>
        </div>
      ))}
      <div className="flex justify-between items-center mt-6">
        <label className="cursor-pointer label">
          <span className="label-text">Process as Chat</span>
          <input type="checkbox" className="checkbox checkbox-primary" checked={isChat} onChange={() => setIsChat(!isChat)} />
        </label>
        <button
          className={`btn btn-accent ${selectedDocuments.size === 0 ? 'btn-disabled' : ''}`}
          onClick={handleIndexSelectedDocuments}
        >
          Index Selected Documents
        </button>
      </div>
    </div>
  );
};

export default SelfieManager;
