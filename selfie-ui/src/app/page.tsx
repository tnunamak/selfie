"use client";

import React, { useState, useEffect, useMemo } from 'react';
import {ChevronDownIcon, ChevronUpIcon} from "@heroicons/react/20/solid";
import CodeSnippet from "@/app/components/CodeSnippet";

const SelfieManager = () => {
  const [dataSources, setDataSources] = useState([]);
  const [documents, setDocuments] = useState({});
  const [selectedDocuments, setSelectedDocuments] = useState(new Set());
  const [isChat, setIsChat] = useState(true);
  const [loading, setLoading] = useState(true);

  const [isTaskPending, setIsTaskPending] = useState(false);
  const [completedTaskMessage, setCompletedTaskMessage] = useState('');
  const [isTaskError, setIsTaskError] = useState(false);

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
    await fetchDocuments(sourceId);
  };

  const handleIndex = async (sourceId) => {
    await fetch(`http://localhost:8181/v1/data-sources/${sourceId}/index`, { method: 'POST' });
  };

  // const handleIndexSelectedDocuments = async () => {
  //   setIsTaskPending(true);
  //
  //   const documentIds = Array.from(selectedDocuments);
  //
  //   try {
  //     const response = await fetch('http://localhost:8181/v1/documents/index', {
  //       method: 'POST',
  //       headers: { 'Content-Type': 'application/json' },
  //       body: JSON.stringify({ document_ids: documentIds, is_chat: isChat })
  //     });
  //
  //     if (!response.ok) {
  //       throw new Error(`Error: ${response.statusText}`);
  //     }
  //
  //     const result = await response.json();
  //     setCompletedTaskMessage('Indexing completed successfully.');
  //   } catch (error) {
  //     setCompletedTaskMessage('Error occurred during indexing.');
  //     console.error('Error indexing documents:', error);
  //   } finally {
  //     setIsTaskPending(false);
  //   }
  // };


  const toggleDocumentSelection = (docId) => {
    setSelectedDocuments(prevSelectedDocuments => {
      const newSelection = new Set(prevSelectedDocuments);
      if (newSelection.has(docId)) {
        newSelection.delete(docId);
      } else {
        newSelection.add(docId);
      }
      return newSelection;
    });
  };

  const columnNames = useMemo(() => {
    const firstDoc = documents[dataSources[0]?.id]?.[0];
    return firstDoc ? Object.keys(firstDoc.metadata) : [];
  }, [documents, dataSources]);

  const toTitleCase = (str) => {
    return str.replace(/_/g, ' ').replace(/\b(\w)/g, char => char.toUpperCase());
  };

  const isNumeric = (str) => {
    if (typeof str == "string") return false;
    return !isNaN(str) && !isNaN(parseFloat(str));
  };

  const isDateString = (str) => {
    return typeof str === 'string' && !isNaN(Date.parse(str));
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
  };

  const TableRow = React.memo(({ doc, dataSource, columnNames, onToggle, isSelected = false }) => {
    // Local state for managing selection status of this row
    const [selected, setSelected] = useState(isSelected);

    useEffect(() => {
      // Update local state if the global selection state changes
      setSelected(isSelected);
    }, [isSelected]);

    const handleCheckboxChange = () => {
      setSelected(!selected); // Toggle local state
      onToggle(doc.id);       // Update global state
    };

    console.log(doc)

    return (
      <tr className={`text-xs ${selected ? 'bg-base-200' : ''}`}>
        <td className="p-2">
          <input
            type="checkbox"
            checked={selected}
            onChange={handleCheckboxChange}
            className="checkbox"
          />
        </td>
        <td className="p-2">
          <div className="truncate max-w-xs" title={dataSource.name}>
            {dataSource.name}
          </div>
        </td>
        <td className="p-2">
          <div className="truncate max-w-xs flex justify-center" title={dataSource.name}>
            <div>
            {doc.is_indexed ? '✅' : ''}
            </div>
          </div>
        </td>
        {columnNames.map((colName) => (
          <td key={`${doc.id}-${colName}`} className={`p-2 ${colName}`}>
            <div className="truncate max-w-xs" title={doc.metadata[colName]}>
              {isDateString(doc.metadata[colName]) ? formatDate(doc.metadata[colName]) : doc.metadata[colName]}
            </div>
          </td>
        ))}
        <td>
          {!doc.is_indexed && <button
            onClick={() => handleIndexDocument(doc.id)}
            className="btn btn-xs"
          >
            Index
          </button>}
          {doc.is_indexed && <button
            onClick={() => handleIndexDocument(doc.id, true)}
            className="btn btn-xs btn-error btn-outline"
          >
            Unindex
          </button>}
        </td>
      </tr>
    );
  });

  const [selectAll, setSelectAll] = useState(false);

  const handleToggleSelectAll = () => {
    setSelectAll(!selectAll);
    if (!selectAll) {
      const allDocIds = Object.values(documents).flat().map(doc => doc.id);
      setSelectedDocuments(new Set(allDocIds));
    } else {
      setSelectedDocuments(new Set());
    }
  };
  const [selectedDirectory, setSelectedDirectory] = useState(null);
  const [dataSourceName, setDataSourceName] = useState('');

  const handleDataSourceNameChange = (event) => {
    setDataSourceName(event.target.value);
  };

  const handleDirectoryChange = (event) => {
    const files = event.target.files;
    const path = files[0]?.webkitRelativePath.split('/')[0]; // Get directory name
    console.log(files)
    console.log('Selected directory:', path);
    setSelectedDirectory(path);
  };
  const handleAddDataSource = async () => {
    try {
      const response = await fetch('http://localhost:8181/v1/data-sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: dataSourceName,
          loader_module: "llama_index.readers.SimpleDirectoryReader",
          // config: {
          constructor_args: [],
          constructor_kwargs: {
            input_dir: selectedDirectory,
            recursive: true
          },
          load_data_args: [],
          load_data_kwargs: {}
          // }
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      const result = await response.json();
      console.log("Data source added:", result);

      // Now, scan the directory to populate the list of documents
      await handleScan(result.id);

      // Optionally, refresh the list of data sources or update the UI accordingly
      await fetchDataSources();
    } catch (error) {
      console.error("Failed to add data source:", error);
    }
  };

  const handleIndexDocument = async (documentId, deleteInstead = false) => {
    await handleIndexSelected([documentId], deleteInstead);
  };


  const handleIndexSelected = async (documentIds = Array.from(selectedDocuments), deleteInstead = false) => {
    setIsTaskPending(true);
    console.log(`${deleteInstead ? 'Unindexing' : 'Indexing'} documents:`, documentIds);

    try {
      const response = await fetch(`http://localhost:8181/v1/documents/${ deleteInstead ? 'unindex' : 'index'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_ids: documentIds.map(id => id.toString()),
          ...(deleteInstead ? {} : {is_chat: isChat})
        })
      });

      if (!response.ok) {
        throw new Error(`Error: ${response.statusText}`);
      }

      const result = await response.json();
      setCompletedTaskMessage(`${ deleteInstead ? 'Unindexing' : 'Indexing' } completed successfully.`);
      // Update the list of documents to reflect the indexing status
      await fetchDataSources();
    } catch (error) {
      setCompletedTaskMessage(`Error occurred during ${ deleteInstead ? 'unindexing' : 'indexing' }.`);
      setIsTaskError(true);
      console.error(`Error ${ deleteInstead ? 'un': '' }indexing documents:`, error);
    } finally {
      setIsTaskPending(false);
    }
  };



  const [sortField, setSortField] = useState(null);
  const [sortDirection, setSortDirection] = useState('asc');

  const handleHeaderClick = (fieldName) => {
    if (sortField === fieldName) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(fieldName);
      setSortDirection('asc');
    }
  };

  const getSortableValue = (value) => {
    if (isDateString(value)) {
      return new Date(value).getTime();
    } else if (isNumeric(value)) {
      return parseFloat(value);
    }
    return value.toString();
  };

  const sortedDocuments = useMemo(() => {
    if (!sortField) return documents;

    return Object.keys(documents).reduce((sortedDocs, key) => {
      sortedDocs[key] = [...documents[key]].sort((a, b) => {
        const aValue = getSortableValue(a.metadata[sortField]);
        const bValue = getSortableValue(b.metadata[sortField]);

        if (sortDirection === 'asc') {
          return aValue > bValue ? 1 : -1;
        } else {
          return aValue < bValue ? 1 : -1;
        }
      });
      return sortedDocs;
    }, {});
  }, [documents, sortField, sortDirection]);

  const handleDeleteDataSource = async (dataSourceId) => {
    try {
      const response = await fetch(`http://localhost:8181/v1/data-sources/${dataSourceId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      // Refresh the list of data sources to reflect the deletion
      await Promise.all([fetchDataSources(), fetchDocuments(dataSourceId)]);
    } catch (error) {
      console.error("Failed to delete data source:", error);
    }
  };

  useEffect(() => {
    if (!completedTaskMessage) {
      return;
    }

    setTimeout(() => {
      setIsTaskPending(false);
      setIsTaskError(false);
      setCompletedTaskMessage('');
    }, 5000);
  }, [completedTaskMessage]);

  if (loading) return <div>Loading data sources...</div>;

  const jsExample = (<CodeSnippet snippet={`import OpenAI from 'openai';

const openai = new OpenAI({
  baseURL: 'http://localhost:8181/v1/memory/v1',
  apiKey: ''
});

const name = 'Alice';
const chatCompletion = await openai.chat.completions.create({
  // model: 'TheBloke/Mistral-7B-Instruct-v0.2-GGUF/mistral-7b-instruct-v0.2.Q5_K_M.gguf', // Optionally, customize the model used
  messages: [
    { role: 'system', content: \`Write $\{name\}'s next reply in a fictional chat with $\{name\} and their friends.\` },
    { role: 'user', content: 'Favorite ice cream?' },
  ]
} as any);

console.log(chatCompletion.choices[0].message.content);
// "Alice enjoys Bahn Mi and Vietnamese coffee."
`} />);
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-4xl font-bold mb-4">Usage</h1>
      <section className="mb-8">
        <p className="mb-4">To get started, add a directory containing chat files, then index one or more documents to
          add them to the knowledge bank.</p>
        <p>
          Once indexed, data will be used automatically in chat completions.
          {jsExample}
        </p>
        <p>
          Explore and test the full set of API features for indexed data on <a className="link"
                                                                               href="http://localhost:8181/docs"
                                                                               target="_blank" rel="noreferrer">the
          documentation page</a>.
          For a quick start, try the <a className="link"
                                        href="http://localhost:8181/docs#/default/get_index_documents_summary_v1_index_documents_summary_get"
                                        target="_blank" rel="noreferrer">Summary API</a>.
        </p>
      </section>
      <h1 className="text-4xl font-bold mb-4">Source Directories</h1>
      <div className="flex flex-wrap items-center mb-4">
        <label className="label mr-2">
          <span className="label-text">Name:</span>
        </label>
        <input
          type="text"
          placeholder="Enter Name"
          value={dataSourceName}
          onChange={handleDataSourceNameChange}
          className="input input-bordered w-full max-w-xs mr-2"
        />

        <label className="label mr-2">
          <span className="label-text">Directory Path:</span>
        </label>
        <input
          type="text"
          placeholder="Absolute Directory Path"
          value={selectedDirectory}
          onChange={(e) => setSelectedDirectory(e.target.value)}
          className="input input-bordered w-full max-w-xs mr-2"
        />

        <button
          onClick={handleAddDataSource}
          className="btn btn-primary"
          disabled={!dataSourceName || !selectedDirectory}
        >
          Add Directory
        </button>
      </div>

      <div className="overflow-x-auto mb-8">
        <table className="table w-full">
          <thead>
          <tr>
            <th>Name</th>
            <th>Input Directory</th>
            <th>Actions</th>
          </tr>
          </thead>
          <tbody>
          {dataSources.filter(d => d.loader_module === 'llama_index.readers.SimpleDirectoryReader').map((dataSource, index) => (
            <tr key={index}>
              <td>{dataSource.name}</td>
              <td>{dataSource.config.constructor_kwargs.input_dir}</td>
              <td>
                <button
                  onClick={() => handleDeleteDataSource(dataSource.id)}
                  className="btn btn-error btn-xs"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
          </tbody>
        </table>
      </div>

      <h1 className="text-4xl font-bold mb-4">Documents</h1>

      {isTaskPending ? (
        <div className="my-4">
          <progress className="progress w-46"></progress>
        </div>
      ) : completedTaskMessage && (
        <div className="toast toast-top toast-end">
          <div className={`alert alert-${isTaskError ? 'error' : 'info'}`}>
            <span>{completedTaskMessage}</span>
          </div>
        </div>
      )}

      <button className="btn mr-4" onClick={() => handleIndexSelected()}
              disabled={selectedDocuments.size === 0 || isTaskPending}>
        Index Documents
      </button>
      <button className="btn btn-error btn-outline" onClick={() => handleIndexSelected(undefined, true)}
              disabled={selectedDocuments.size === 0 || isTaskPending}>
        Unindex Documents
      </button>
      <div className="overflow-x-auto">
        <table className="table w-full">
          <thead>
          <tr className="cursor-pointer">
            <th className="p-2" style={{lineHeight: 0}}>
              <input
                type="checkbox"
                checked={selectAll}
                onChange={handleToggleSelectAll}
                className="checkbox"
              />
            </th>
            {/* TODO: make sortable */}
            <th className="p-2 cursor-default">
              Source
            </th>
            <th className="p-2 cursor-default">
              Is Indexed
            </th>
            {columnNames.map((colName) => (
              <th key={colName} onClick={() => handleHeaderClick(colName)}>
                {toTitleCase(colName)}
                {sortField === colName && (
                  sortDirection === 'asc' ? <ChevronUpIcon className="h-4 w-4 float-right"/> :
                    <ChevronDownIcon className="h-4 w-4 float-right"/>
                )}
              </th>
            ))}
            <th>Actions</th>
          </tr>
          </thead>
          <tbody>
          {dataSources.flatMap(dataSource =>
            sortedDocuments[dataSource.id]?.map(doc => (
              <TableRow
                key={doc.id}
                doc={doc}
                dataSource={dataSource}
                columnNames={columnNames}
                isSelected={selectedDocuments.has(doc.id)}
                onToggle={toggleDocumentSelection}
              />
            ))
          )}
          </tbody>

        </table>
      </div>
    </div>
  );
};

export default SelfieManager;
