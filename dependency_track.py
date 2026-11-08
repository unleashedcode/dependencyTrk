#!/usr/bin/env python3
"""
C++ Dependency Tracker - Analyzes #include relationships in C++ projects

This tool scans C++ source code to find all #include dependencies between files
and creates visual graphs showing how classes and files are interconnected.

Requirements:
    pip install networkx matplotlib

Usage:
    python dependency_tracker.py

Author: Improved version for Unreal Engine C++ development
"""

import os
import re
import sys
import threading
from pathlib import Path
from typing import Dict, Set, List, Tuple, Optional
from collections import defaultdict
from tkinter import *
from tkinter import ttk, filedialog, messagebox, scrolledtext
import tkinter as tk

import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class FileAnalyzer:
    """
    Handles the analysis of individual C++ files to extract includes and classes.
    
    This class is responsible for:
    - Finding #include statements in C++ files
    - Extracting class definitions
    - Handling file reading with proper error handling
    """
    
    def __init__(self):
        """Initialize regex patterns for finding includes and classes."""
        # Pattern to match #include statements: #include "file.h" or #include <file.h>
        self.include_pattern = re.compile(r'^\s*#include\s*[<"]([^<>"]+)[>"]', re.MULTILINE)
        
        # Pattern to match class declarations: class ClassName
        self.class_pattern = re.compile(r'^\s*class\s+(\w+)', re.MULTILINE)
        
    def extract_includes(self, file_path: Path) -> Set[str]:
        """
        Extract all #include statements from a C++ file.
        
        Args:
            file_path: Path to the C++ file to analyze
            
        Returns:
            Set of included file names (without path)
        """
        try:
            # Read file with UTF-8 encoding, ignore encoding errors
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Find all #include matches and extract the filename
            includes = set()
            matches = self.include_pattern.findall(content)
            for match in matches:
                include_file = match.strip()
                includes.add(include_file)
            
            return includes
            
        except Exception as e:
            # If file can't be read, return empty set
            print(f"Warning: Could not read {file_path}: {e}")
            return set()
    
    def extract_classes(self, file_path: Path) -> Set[str]:
        """
        Extract all class definitions from a C++ file.
        
        Args:
            file_path: Path to the C++ file to analyze
            
        Returns:
            Set of class names found in the file
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Find all class declarations and extract class names
            classes = set()
            matches = self.class_pattern.findall(content)
            for match in matches:
                classes.add(match.strip())
            
            return classes
            
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            return set()


class ProjectScanner:
    """
    Scans a project directory to find all C++ files.
    
    This class handles:
    - Walking through directory structures
    - Identifying C++ source and header files
    - Filtering files by extension
    """
    
    def __init__(self):
        """Initialize with common C++ file extensions."""
        # Common C++ file extensions
        self.cpp_extensions = {'.cpp', '.cxx', '.cc', '.c++', '.h', '.hpp', '.hxx', '.h++'}
        
    def find_cpp_files(self, project_path: Path) -> List[Path]:
        """
        Find all C++ source and header files in the project directory.
        
        Args:
            project_path: Root directory to scan
            
        Returns:
            List of Path objects for all C++ files found
        """
        cpp_files = []
        
        # Walk through all subdirectories
        for root, dirs, files in os.walk(project_path):
            for file in files:
                # Check if file has a C++ extension
                if any(file.endswith(ext) for ext in self.cpp_extensions):
                    cpp_files.append(Path(root) / file)
        
        return cpp_files


class DependencyAnalyzer:
    """
    Main class for analyzing C++ project dependencies.
    
    This class orchestrates the entire analysis process:
    - Scanning for C++ files
    - Extracting includes and classes
    - Building dependency relationships
    - Creating NetworkX graphs for visualization
    """
    
    def __init__(self):
        """Initialize the analyzer with helper classes and data structures."""
        self.project_path: Optional[Path] = None
        self.file_analyzer = FileAnalyzer()
        self.project_scanner = ProjectScanner()
        
        # Data structures to store analysis results
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)  # file -> set of included files
        self.file_to_classes: Dict[str, Set[str]] = defaultdict(set)  # file -> set of classes
        self.class_to_file: Dict[str, str] = {}  # class -> file containing it
        self.all_files: Set[str] = set()  # all files in project (relative paths)
        self.graph: Optional[nx.DiGraph] = None  # NetworkX graph
        
    def analyze_project(self, progress_callback=None) -> bool:
        """
        Analyze the entire project for dependencies and classes.
        
        Args:
            progress_callback: Optional function to call with progress updates
            
        Returns:
            True if analysis succeeded, False otherwise
        """
        if not self.project_path:
            return False
            
        # Find all C++ files in the project
        cpp_files = self.project_scanner.find_cpp_files(self.project_path)
        
        if not cpp_files:
            return False
        
        total_files = len(cpp_files)
        
        # First pass: collect all files and their classes
        for i, file_path in enumerate(cpp_files):
            if progress_callback:
                progress_callback(f"Analyzing classes... ({i+1}/{total_files})", 
                                (i+1) / total_files * 50)
            
            # Convert to relative path for consistency
            rel_path = file_path.relative_to(self.project_path)
            rel_path_str = str(rel_path)
            self.all_files.add(rel_path_str)
            
            # Extract classes from this file
            classes = self.file_analyzer.extract_classes(file_path)
            self.file_to_classes[rel_path_str] = classes
            
            # Map each class to its containing file
            for class_name in classes:
                self.class_to_file[class_name] = rel_path_str
        
        # Second pass: collect dependencies
        for i, file_path in enumerate(cpp_files):
            if progress_callback:
                progress_callback(f"Analyzing dependencies... ({i+1}/{total_files})", 
                                50 + (i+1) / total_files * 50)
            
            rel_path = file_path.relative_to(self.project_path)
            rel_path_str = str(rel_path)
            
            # Extract includes from this file
            includes = self.file_analyzer.extract_includes(file_path)
            
            # Match includes to actual project files
            project_includes = self._match_includes_to_files(includes)
            self.dependencies[rel_path_str] = project_includes
        
        return True
    
    def _match_includes_to_files(self, includes: Set[str]) -> Set[str]:
        """
        Match #include statements to actual files in the project.
        
        Args:
            includes: Set of include filenames from #include statements
            
        Returns:
            Set of actual project file paths that match the includes
        """
        project_includes = set()
        
        for include in includes:
            # Try to match include to actual project files
            for project_file in self.all_files:
                # Check if the include matches the end of the project file path
                if project_file.endswith(include) or include.endswith(Path(project_file).name):
                    project_includes.add(project_file)
                    break
        
        return project_includes
    
    def create_dependency_graph(self) -> nx.DiGraph:
        """
        Create a NetworkX directed graph of dependencies.
        
        Returns:
            NetworkX DiGraph with nodes representing files and edges representing dependencies
        """
        G = nx.DiGraph()
        
        # Add nodes for files that contain classes
        for file_path, classes in self.file_to_classes.items():
            if classes:
                # Create a nice label showing filename and classes
                class_list = ', '.join(sorted(classes))
                label = f"{Path(file_path).stem}\n({class_list})"
                G.add_node(file_path, label=label, classes=classes)
        
        # Add edges for dependencies
        for source_file, included_files in self.dependencies.items():
            if source_file in G.nodes():  # Only if source file has classes
                for included_file in included_files:
                    if included_file in G.nodes():  # Only if target file has classes
                        G.add_edge(source_file, included_file)
        
        self.graph = G
        return G
    
    def get_statistics(self) -> Dict:
        """
        Get analysis statistics for display.
        
        Returns:
            Dictionary containing various statistics about the project
        """
        if not self.graph:
            return {}
        
        G = self.graph
        stats = {
            'total_files': len(G.nodes()),
            'total_dependencies': len(G.edges()),
            'total_classes': len(self.class_to_file)
        }
        
        if len(G.nodes()) > 0:
            # Calculate degree statistics
            in_degrees = dict(G.in_degree())
            out_degrees = dict(G.out_degree())
            
            # Find most included files (files that many others depend on)
            stats['most_included'] = sorted(in_degrees.items(), 
                                          key=lambda x: x[1], reverse=True)[:5]
            
            # Find files with most dependencies (files that depend on many others)
            stats['most_dependent'] = sorted(out_degrees.items(), 
                                           key=lambda x: x[1], reverse=True)[:5]
            
            # Check for circular dependencies
            try:
                cycles = list(nx.simple_cycles(G))
                stats['circular_dependencies'] = len(cycles)
                stats['cycles'] = cycles[:3]  # Show first 3 cycles
            except:
                stats['circular_dependencies'] = 0
                stats['cycles'] = []
        
        return stats


class GraphVisualizer:
    """
    Handles the creation and styling of dependency graphs.
    
    This class is responsible for:
    - Creating different graph layouts
    - Applying modern styling and colors
    - Handling node and edge appearance
    - Creating legends and labels
    """
    
    def __init__(self):
        """Initialize with modern color scheme."""
        # Modern color palette
        self.colors = {
            'header': '#3498db',      # Modern blue for header files
            'source': '#e74c3c',      # Modern red for source files
            'edge': '#95a5a6',        # Modern gray for edges
            'background': '#fafafa',   # Light background
            'text': '#2c3e50'         # Dark text
        }
    
    def create_graph_visualization(self, G: nx.DiGraph, layout_type: str, 
                                 filter_type: str, show_labels: bool) -> Figure:
        """
        Create a matplotlib figure with the dependency graph.
        
        Args:
            G: NetworkX graph to visualize
            layout_type: Type of layout ('hierarchical', 'circular', etc.)
            filter_type: Type of filter applied
            show_labels: Whether to show node labels
            
        Returns:
            Matplotlib Figure object
        """
        # Apply filtering first
        G = self._apply_filter(G, filter_type)
        
        if len(G.nodes()) == 0:
            return self._create_empty_figure("No nodes match the current filter!")
        
        # Create matplotlib figure
        fig = Figure(figsize=(14, 10), dpi=100, facecolor=self.colors['background'])
        ax = fig.add_subplot(111, facecolor=self.colors['background'])
        
        # Get node positions based on layout type
        pos = self._get_layout_positions(G, layout_type)
        
        # Separate nodes by file type
        header_nodes, source_nodes = self._separate_nodes_by_type(G)
        
        # Draw nodes with modern styling
        self._draw_nodes(G, pos, ax, header_nodes, source_nodes)
        
        # Draw edges with arrows
        self._draw_edges(G, pos, ax)
        
        # Add labels if requested
        if show_labels:
            self._draw_labels(G, pos, ax)
        
        # Add title and legend
        self._add_title_and_legend(ax, filter_type, layout_type, header_nodes, source_nodes, G)
        
        # Clean up the plot appearance
        ax.axis('off')
        fig.tight_layout(pad=1.5)
        
        return fig
    
    def _apply_filter(self, G: nx.DiGraph, filter_type: str) -> nx.DiGraph:
        """Apply the selected filter to the graph."""
        if filter_type == "all":
            return G
        elif filter_type == "headers_only":
            header_nodes = [n for n in G.nodes() if self._is_header_file(n)]
            return G.subgraph(header_nodes)
        elif filter_type == "sources_only":
            source_nodes = [n for n in G.nodes() if not self._is_header_file(n)]
            return G.subgraph(source_nodes)
        elif filter_type == "highly_connected":
            # Show only nodes with 2 or more connections
            high_degree_nodes = [n for n in G.nodes() if G.degree(n) >= 2]
            return G.subgraph(high_degree_nodes)
        
        return G
    
    def _is_header_file(self, filename: str) -> bool:
        """Check if a file is a header file based on extension."""
        return filename.endswith(('.h', '.hpp', '.hxx', '.h++'))
    
    def _get_layout_positions(self, G: nx.DiGraph, layout_type: str) -> Dict:
        """Get node positions based on the selected layout type."""
        if layout_type == "hierarchical":
            return self._create_hierarchical_layout(G)
        elif layout_type == "circular":
            return nx.circular_layout(G, scale=2)
        elif layout_type == "spring":
            return nx.spring_layout(G, k=2, iterations=100, seed=42)
        elif layout_type == "shell":
            return nx.shell_layout(G, scale=2)
        else:
            return nx.spring_layout(G, k=2, iterations=50, seed=42)
    
    def _create_hierarchical_layout(self, G: nx.DiGraph) -> Dict:
        """Create a hierarchical layout with headers at top, sources at bottom."""
        pos = {}
        
        # Separate nodes by type
        header_nodes = [n for n in G.nodes() if self._is_header_file(n)]
        source_nodes = [n for n in G.nodes() if not self._is_header_file(n)]
        
        # Position headers at top
        if header_nodes:
            if len(header_nodes) == 1:
                pos[header_nodes[0]] = (0, 2)
            else:
                header_pos = nx.spring_layout(G.subgraph(header_nodes), k=1.5, seed=42)
                for node, position in header_pos.items():
                    pos[node] = (position[0] * 3, position[1] + 2)
        
        # Position sources at bottom
        if source_nodes:
            if len(source_nodes) == 1:
                pos[source_nodes[0]] = (0, -2)
            else:
                source_pos = nx.spring_layout(G.subgraph(source_nodes), k=1.5, seed=42)
                for node, position in source_pos.items():
                    pos[node] = (position[0] * 3, position[1] - 2)
        
        return pos
    
    def _separate_nodes_by_type(self, G: nx.DiGraph) -> Tuple[List[str], List[str]]:
        """Separate graph nodes into header files and source files."""
        header_nodes = [n for n in G.nodes() if self._is_header_file(n)]
        source_nodes = [n for n in G.nodes() if not self._is_header_file(n)]
        return header_nodes, source_nodes
    
    def _draw_nodes(self, G: nx.DiGraph, pos: Dict, ax, header_nodes: List[str], source_nodes: List[str]):
        """Draw graph nodes with modern styling."""
        if header_nodes:
            nx.draw_networkx_nodes(G, pos, nodelist=header_nodes, ax=ax,
                                  node_color=self.colors['header'],
                                  node_size=1200,
                                  alpha=0.9,
                                  edgecolors='white',
                                  linewidths=2)
        
        if source_nodes:
            nx.draw_networkx_nodes(G, pos, nodelist=source_nodes, ax=ax,
                                  node_color=self.colors['source'],
                                  node_size=1200,
                                  alpha=0.9,
                                  edgecolors='white',
                                  linewidths=2)
    
    def _draw_edges(self, G: nx.DiGraph, pos: Dict, ax):
        """Draw graph edges with arrows."""
        nx.draw_networkx_edges(G, pos, ax=ax,
                              edge_color=self.colors['edge'],
                              arrows=True,
                              arrowsize=12,
                              arrowstyle='-|>',
                              alpha=0.6,
                              width=1.2,
                              connectionstyle="arc3,rad=0.1",
                              min_target_margin=15,
                              min_source_margin=15)
    
    def _draw_labels(self, G: nx.DiGraph, pos: Dict, ax):
        """Draw node labels with clean formatting."""
        labels = self._create_clean_labels(G)
        
        for node, label in labels.items():
            x, y = pos[node]
            ax.text(x, y, label, 
                   horizontalalignment='center',
                   verticalalignment='center',
                   fontsize=8,
                   fontweight='bold',
                   color='white',
                   bbox=dict(boxstyle="round,pad=0.2", 
                            facecolor='black', 
                            alpha=0.8,
                            edgecolor='none'))
    
    def _create_clean_labels(self, G: nx.DiGraph) -> Dict[str, str]:
        """Create clean, readable labels for nodes."""
        labels = {}
        
        for node in G.nodes():
            filename = Path(node).stem
            classes = G.nodes[node].get('classes', set())
            
            # Create concise labels
            if len(classes) == 1:
                class_name = list(classes)[0]
                # Truncate long class names
                if len(class_name) > 12:
                    class_name = class_name[:12] + "..."
                labels[node] = f"{filename}\n[{class_name}]"
            elif len(classes) > 1:
                labels[node] = f"{filename}\n({len(classes)} classes)"
            else:
                labels[node] = filename
        
        return labels
    
    def _add_title_and_legend(self, ax, filter_type: str, layout_type: str, 
                            header_nodes: List[str], source_nodes: List[str], G: nx.DiGraph):
        """Add title and legend to the graph."""
        # Create title
        filter_name = filter_type.replace('_', ' ').title()
        layout_name = layout_type.title()
        title = f"C++ Dependencies - {filter_name} ({layout_name} Layout)"
        
        ax.set_title(title, 
                    fontsize=14, 
                    fontweight='bold',
                    color=self.colors['text'],
                    pad=15)
        
        # Create legend
        legend_elements = []
        if header_nodes:
            legend_elements.append(plt.Line2D([0], [0], marker='o', color='w', 
                                             markerfacecolor=self.colors['header'], markersize=10,
                                             label=f'Headers ({len(header_nodes)})'))
        if source_nodes:
            legend_elements.append(plt.Line2D([0], [0], marker='o', color='w', 
                                             markerfacecolor=self.colors['source'], markersize=10,
                                             label=f'Sources ({len(source_nodes)})'))
        
        # Add edge count to legend
        legend_elements.append(plt.Line2D([0], [0], color=self.colors['edge'], alpha=0.6,
                                         label=f'Dependencies ({len(G.edges())})'))
        
        if legend_elements:
            ax.legend(handles=legend_elements, 
                     loc='upper left',
                     frameon=True,
                     fancybox=True,
                     shadow=True,
                     framealpha=0.9,
                     fontsize=9)
    
    def _create_empty_figure(self, message: str) -> Figure:
        """Create an empty figure with a message."""
        fig = Figure(figsize=(8, 6), facecolor=self.colors['background'])
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, message, 
               horizontalalignment='center',
               verticalalignment='center',
               fontsize=12,
               transform=ax.transAxes)
        ax.axis('off')
        return fig


class DependencyTrackerGUI:
    """
    Main GUI class for the C++ Dependency Tracker application.
    
    This class handles:
    - Creating the user interface
    - Managing user interactions
    - Coordinating between analysis and visualization components
    - Displaying results in multiple tabs
    """
    
    def __init__(self, root):
        """Initialize the GUI application."""
        self.root = root
        self.root.title("C++ Dependency Tracker")
        self.root.geometry("1000x700")
        self.root.configure(bg='#f0f0f0')
        
        # Initialize components
        self.analyzer = DependencyAnalyzer()
        self.visualizer = GraphVisualizer()
        self.current_figure = None
        
        # GUI variables
        self.path_var = StringVar()
        self.layout_var = StringVar(value="hierarchical")
        self.filter_var = StringVar(value="all")
        self.show_labels_var = BooleanVar(value=True)
        self.progress_var = StringVar(value="Ready to analyze...")
        
        self.setup_gui()
        
    def setup_gui(self):
        """Set up the complete GUI interface."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(W, E, N, S))
        
        # Configure grid weights for responsive design
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        self._create_title(main_frame)
        self._create_project_selection(main_frame)
        self._create_tabs(main_frame)
        
    def _create_title(self, parent):
        """Create the application title."""
        title_label = ttk.Label(parent, text="C++ Dependency Tracker", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
    def _create_project_selection(self, parent):
        """Create the project selection section."""
        project_frame = ttk.LabelFrame(parent, text="Project Selection", padding="10")
        project_frame.grid(row=1, column=0, columnspan=3, sticky=(W, E), pady=(0, 10))
        project_frame.columnconfigure(1, weight=1)
        
        # Path selection
        ttk.Label(project_frame, text="Project Path:").grid(row=0, column=0, sticky=W)
        
        self.path_entry = ttk.Entry(project_frame, textvariable=self.path_var, width=50)
        self.path_entry.grid(row=0, column=1, sticky=(W, E), padx=(10, 10))
        
        self.browse_button = ttk.Button(project_frame, text="Browse", 
                                       command=self.browse_folder)
        self.browse_button.grid(row=0, column=2, sticky=W)
        
        # Analyze button
        self.analyze_button = ttk.Button(project_frame, text="Analyze Project", 
                                        command=self.start_analysis)
        self.analyze_button.grid(row=1, column=0, columnspan=3, pady=(10, 0))
        
        # Progress indicators
        self.progress_label = ttk.Label(project_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=2, column=0, columnspan=3, pady=(5, 0))
        
        self.progress_bar = ttk.Progressbar(project_frame, mode='determinate')
        self.progress_bar.grid(row=3, column=0, columnspan=3, sticky=(W, E), pady=(5, 0))
        
    def _create_tabs(self, parent):
        """Create the tabbed interface for results."""
        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=2, column=0, columnspan=3, sticky=(W, E, N, S), pady=(10, 0))
        
        # Create individual tabs
        self._create_graph_tab()
        self._create_stats_tab()
        self._create_files_tab()
        
    def _create_graph_tab(self):
        """Create the graph visualization tab."""
        self.graph_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.graph_frame, text="Dependency Graph")
        
        self.graph_frame.columnconfigure(0, weight=1)
        self.graph_frame.rowconfigure(1, weight=1)
        
        # Control panel for graph options
        self._create_graph_controls(self.graph_frame)
        
        # Placeholder for graph
        self.graph_placeholder = ttk.Label(self.graph_frame, 
                                          text="Select a project folder and click 'Analyze Project' to view dependencies",
                                          font=('Arial', 12))
        self.graph_placeholder.grid(row=1, column=0, sticky=(W, E, N, S))
        
    def _create_graph_controls(self, parent):
        """Create the control panel for graph visualization options."""
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=0, column=0, sticky=(W, E), pady=(5, 10))
        
        # Layout selection
        ttk.Label(control_frame, text="Layout:").pack(side=LEFT, padx=(0, 5))
        
        layout_combo = ttk.Combobox(control_frame, textvariable=self.layout_var, 
                                   values=["hierarchical", "circular", "spring", "shell"],
                                   state="readonly", width=12)
        layout_combo.pack(side=LEFT, padx=(0, 15))
        layout_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_graph())
        
        # Filter selection
        ttk.Label(control_frame, text="Filter:").pack(side=LEFT, padx=(0, 5))
        
        filter_combo = ttk.Combobox(control_frame, textvariable=self.filter_var,
                                   values=["all", "headers_only", "sources_only", "highly_connected"],
                                   state="readonly", width=15)
        filter_combo.pack(side=LEFT, padx=(0, 15))
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_graph())
        
        # Action buttons
        self.save_button = ttk.Button(control_frame, text="Save PNG", 
                                     command=self.save_graph, state='disabled')
        self.save_button.pack(side=LEFT, padx=(0, 10))
        
        self.refresh_button = ttk.Button(control_frame, text="Refresh", 
                                        command=self.refresh_graph, state='disabled')
        self.refresh_button.pack(side=LEFT)
        
        # Show labels toggle
        labels_check = ttk.Checkbutton(control_frame, text="Show Labels", 
                                      variable=self.show_labels_var,
                                      command=self.refresh_graph)
        labels_check.pack(side=RIGHT, padx=(10, 0))
        
    def _create_stats_tab(self):
        """Create the statistics display tab."""
        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text="Statistics")
        
        self.stats_frame.columnconfigure(0, weight=1)
        self.stats_frame.rowconfigure(0, weight=1)
        
        self.stats_text = scrolledtext.ScrolledText(self.stats_frame, wrap=tk.WORD, 
                                                   font=('Consolas', 10))
        self.stats_text.grid(row=0, column=0, sticky=(W, E, N, S), padx=5, pady=5)
        
    def _create_files_tab(self):
        """Create the files list tab."""
        self.files_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.files_frame, text="File List")
        
        self.files_frame.columnconfigure(0, weight=1)
        self.files_frame.rowconfigure(0, weight=1)
        
        # Create treeview for file list
        columns = ('File', 'Classes', 'Dependencies', 'Dependents')
        self.files_tree = ttk.Treeview(self.files_frame, columns=columns, show='headings')
        
        for col in columns:
            self.files_tree.heading(col, text=col)
            self.files_tree.column(col, width=200)
        
        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(self.files_frame, orient=tk.VERTICAL, 
                                 command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=scrollbar.set)
        
        self.files_tree.grid(row=0, column=0, sticky=(W, E, N, S), padx=(5, 0), pady=5)
        scrollbar.grid(row=0, column=1, sticky=(N, S), pady=5)
        
    def browse_folder(self):
        """Open folder browser dialog."""
        folder_path = filedialog.askdirectory(title="Select C++ Project Folder")
        if folder_path:
            self.path_var.set(folder_path)
            
    def start_analysis(self):
        """Start the analysis in a separate thread."""
        project_path = self.path_var.get().strip()
        
        if not project_path:
            messagebox.showerror("Error", "Please select a project folder first!")
            return
            
        if not os.path.exists(project_path):
            messagebox.showerror("Error", "Selected folder does not exist!")
            return
        
        self.analyzer.project_path = Path(project_path)
        
        # Disable buttons during analysis
        self.analyze_button.config(state='disabled')
        self.browse_button.config(state='disabled')
        
        # Start analysis in separate thread
        analysis_thread = threading.Thread(target=self.run_analysis)
        analysis_thread.daemon = True
        analysis_thread.start()
        
    def run_analysis(self):
        """Run the analysis and update GUI."""
        def update_progress(message, progress):
            self.root.after(0, lambda: self.update_progress_gui(message, progress))
        
        try:
            success = self.analyzer.analyze_project(update_progress)
            
            if success:
                self.root.after(0, self.analysis_completed)
            else:
                self.root.after(0, lambda: self.analysis_failed("No C++ files found!"))
                
        except Exception as e:
            self.root.after(0, lambda: self.analysis_failed(str(e)))
    
    def update_progress_gui(self, message, progress):
        """Update progress bar and message."""
        self.progress_var.set(message)
        self.progress_bar['value'] = progress
        self.root.update_idletasks()
        
    def analysis_completed(self):
        """Handle successful analysis completion."""
        self.progress_var.set("Analysis completed!")
        self.progress_bar['value'] = 100
        
        # Enable buttons
        self.analyze_button.config(state='normal')
        self.browse_button.config(state='normal')
        self.save_button.config(state='normal')
        self.refresh_button.config(state='normal')
        
        # Update all tabs
        self.update_graph()
        self.update_statistics()
        self.update_files_list()
        
        messagebox.showinfo("Success", "Project analysis completed successfully!")
        
    def analysis_failed(self, error_message):
        """Handle analysis failure."""
        self.progress_var.set("Analysis failed!")
        self.progress_bar['value'] = 0
        
        # Enable buttons
        self.analyze_button.config(state='normal')
        self.browse_button.config(state='normal')
        
        messagebox.showerror("Analysis Failed", f"Error during analysis:\n{error_message}")
    
    def update_graph(self):
        """Update the dependency graph visualization."""
        try:
            G = self.analyzer.create_dependency_graph()
            
            if len(G.nodes()) == 0:
                self.graph_placeholder.config(text="No classes found in the project!")
                return
            
            # Remove placeholder
            self.graph_placeholder.grid_remove()
            
            # Create visualization using the GraphVisualizer
            if self.current_figure:
                self.current_figure.get_tk_widget().destroy()
            
            fig = self.visualizer.create_graph_visualization(
                G, 
                self.layout_var.get(),
                self.filter_var.get(),
                self.show_labels_var.get()
            )
            
            # Embed in tkinter
            canvas = FigureCanvasTkAgg(fig, self.graph_frame)
            canvas.draw()
            canvas.get_tk_widget().grid(row=1, column=0, sticky=(W, E, N, S))
            
            self.current_figure = canvas
            
        except Exception as e:
            messagebox.showerror("Graph Error", f"Error creating graph: {str(e)}")
    
    def update_statistics(self):
        """Update the statistics display."""
        stats = self.analyzer.get_statistics()
        
        self.stats_text.delete(1.0, tk.END)
        
        content = "=== C++ DEPENDENCY ANALYSIS STATISTICS ===\n\n"
        content += f"Total files with classes: {stats.get('total_files', 0)}\n"
        content += f"Total dependencies: {stats.get('total_dependencies', 0)}\n"
        content += f"Total classes found: {stats.get('total_classes', 0)}\n\n"
        
        if stats.get('most_included'):
            content += "MOST INCLUDED FILES:\n"
            for file, count in stats['most_included']:
                if count > 0:
                    classes = ', '.join(self.analyzer.graph.nodes[file].get('classes', []))
                    content += f"  • {Path(file).name} ({classes}): included by {count} files\n"
            content += "\n"
        
        if stats.get('most_dependent'):
            content += "FILES WITH MOST DEPENDENCIES:\n"
            for file, count in stats['most_dependent']:
                if count > 0:
                    classes = ', '.join(self.analyzer.graph.nodes[file].get('classes', []))
                    content += f"  • {Path(file).name} ({classes}): depends on {count} files\n"
            content += "\n"
        
        circular_deps = stats.get('circular_dependencies', 0)
        if circular_deps > 0:
            content += f"⚠️  WARNING: Found {circular_deps} circular dependencies!\n"
            for i, cycle in enumerate(stats.get('cycles', [])):
                cycle_names = [Path(f).name for f in cycle]
                content += f"  Cycle {i+1}: {' → '.join(cycle_names)} → {cycle_names[0]}\n"
        else:
            content += "✅ No circular dependencies found.\n"
        
        self.stats_text.insert(1.0, content)
    
    def update_files_list(self):
        """Update the files list display."""
        # Clear existing items
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        if not self.analyzer.graph:
            return
        
        G = self.analyzer.graph
        
        for file_path in self.analyzer.file_to_classes:
            classes = list(self.analyzer.file_to_classes[file_path])
            classes_str = ', '.join(sorted(classes)) if classes else "None"
            
            # Count dependencies (outgoing edges)
            dependencies = len([edge for edge in G.edges() if edge[0] == file_path])
            
            # Count dependents (incoming edges)
            dependents = len([edge for edge in G.edges() if edge[1] == file_path])
            
            self.files_tree.insert('', tk.END, values=(
                Path(file_path).name,
                classes_str,
                dependencies,
                dependents
            ))
    
    def refresh_graph(self):
        """Refresh the graph display."""
        if self.analyzer.graph:
            self.update_graph()
        
    def save_graph(self):
        """Save the current graph as PNG."""
        if not self.current_figure:
            messagebox.showwarning("No Graph", "No graph to save! Please analyze a project first.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            title="Save Dependency Graph"
        )
        
        if file_path:
            try:
                self.current_figure.figure.savefig(file_path, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Success", f"Graph saved successfully to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Error saving graph:\n{str(e)}")


def main():
    """Main application entry point."""
    try:
        import matplotlib
        matplotlib.use('TkAgg')  # Set backend before importing pyplot
    except ImportError:
        messagebox.showerror("Missing Dependencies", 
                           "Required packages not found!\n\nPlease install:\npip install networkx matplotlib")
        return
    
    root = tk.Tk()
    app = DependencyTrackerGUI(root)
    
    # Configure style
    style = ttk.Style()
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    
    root.mainloop()


if __name__ == "__main__":
    main()