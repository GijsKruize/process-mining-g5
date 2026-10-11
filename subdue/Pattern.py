# Pattern.py
#
# Written by Larry Holder (holder@wsu.edu).
#
# Copyright (c) 2017-2021. Washington State University.
#
# Vendored for the JM0211 assignment. Two functions were rewritten for speed,
# with identical results (see the comments at ExtendPattern and
# InstancesOverlap/OverlapIndex): upstream compares every new instance with
# every other one, which is quadratic in the number of instances of a pattern.
# Our union graph has patterns with thousands of instances (one per trace),
# so the quadratic version dominated the running time of step 3.

from OrderedSet import OrderedSet # specialized Subdue version
import Graph

class Pattern:
    
    def __init__(self):
        self.definition = None # Graph
        self.instances = []
        self.value = 0.0
    
    def evaluate (self, graph):
        """Compute value of using given pattern to compress given graph, where 0 means no compression, and 1 means perfect compression."""
        # (instances-1) because we would also need to retain the definition of the pattern for compression
        self.value = float(((len(self.instances) - 1) * len(self.definition.edges)) / float(len(graph.edges))) 
    
    def print_pattern(self, tab):
        print(tab + "Pattern (value=" + str(self.value) + ", instances=" + str(len(self.instances)) + "):")
        self.definition.print_graph(tab+'  ')
        # May want to make instance printing optional
        instanceNum = 1
        for instance in self.instances:
            instance.print_instance(instanceNum, tab+'  ')
            instanceNum += 1
    
    def write_instances_to_file(self, outputFileName):
        """Write instances of pattern to given file name in JSON format."""
        outputFile = open(outputFileName, 'w')
        outputFile.write('[\n')
        firstOne = True
        for instance in self.instances:
            if firstOne:
                firstOne = False
            else:
                outputFile.write(',\n')
            instance.write_to_file(outputFile)
        outputFile.write('\n]\n')
        outputFile.close()

class Instance:
    
    def __init__(self):
        self.vertices = OrderedSet()
        self.edges = OrderedSet()
    
    def print_instance (self, instanceNum, tab=""):
        print(tab + "Instance " + str(instanceNum) + ":")
        for vertex in self.vertices:
            vertex.print_vertex(tab+'  ')
        for edge in self.edges:
            edge.print_edge(tab+'  ')
            
    def write_to_file(self, outputFile):
        """Write instance to given file stream in JSON format."""
        firstOne = True
        for vertex in self.vertices:
            if firstOne:
                firstOne = False
            else:
                outputFile.write(',\n')
            vertex.write_to_file(outputFile)
        outputFile.write(',\n')
        firstOne = True
        for edge in self.edges:
            if firstOne:
                firstOne = False
            else:
                outputFile.write(',\n')
            edge.write_to_file(outputFile)
    
    def max_timestamp(self):
        """Returns the maximum timestamp over all vertices and edges in the instance."""
        maxTimeStampVertex = max(self.vertices, key = lambda v: v.timestamp)
        maxTimeStampEdge = max(self.edges, key = lambda e: e.timestamp)
        return max(maxTimeStampVertex.timestamp, maxTimeStampEdge.timestamp)
        

# ----- Pattern and Instance Creation

def CreateInstanceFromEdge(edge):
    i = Instance()
    i.edges.add(edge)
    i.vertices.add(edge.source)
    i.vertices.add(edge.target)
    return i

def CreatePatternFromInstances(definition, instances):
    """Create pattern from given definition graph and its instances. Note: Pattern not evaluated here."""
    pattern = Pattern()
    pattern.definition = definition
    pattern.instances = instances
    return pattern

# ----- Pattern Extension

def InstanceKey(instance):
    """Hashable identity of an instance: its vertex objects and its edge objects.
    Two instances have the same key exactly when InstanceMatch() is True."""
    return (frozenset(instance.vertices.set_container), frozenset(instance.edges.set_container))

def InstanceSignature(instance):
    """A cheap invariant of the graph of an instance: the sorted list of
    (source attributes, edge attributes, target attributes, directed) over its
    edges, plus the number of vertices. If Graph.GraphMatch() says two instance
    graphs are isomorphic, their signatures are equal (the matcher maps edges
    one to one and requires equal edge attributes, direction and end-point
    attributes). The converse does not hold, so the signature is only used to
    skip comparisons that cannot succeed, never to accept a match."""
    edgeKeys = []
    for edge in instance.edges:
        sourceKey = tuple(sorted(edge.source.attributes.items()))
        targetKey = tuple(sorted(edge.target.attributes.items()))
        if (not edge.directed) and (targetKey < sourceKey):
            sourceKey, targetKey = targetKey, sourceKey
        edgeKeys.append((sourceKey, tuple(sorted(edge.attributes.items())), targetKey, edge.directed))
    edgeKeys.sort()
    return (len(instance.vertices.list_container), tuple(edgeKeys))

def ExtendPattern (parameters, pattern):
    """Return list of patterns created by extending each instance of the given pattern by one edge in all possible ways,
       and then collecting matching extended instances together into new patterns.

       Speed-up with respect to upstream (same output, same order):
       - duplicate extended instances are detected with a dictionary on InstanceKey
         instead of comparing with every instance collected so far;
       - an instance is only compared (GraphMatch) with a seed instance that has the
         same InstanceSignature, since no other pair can match;
       - the graph of each instance is built once instead of once per comparison;
       - overlap with the instances already in a pattern is checked with an
         OverlapIndex instead of against each of them.
       Seeds are still taken in the original order and candidates are still scanned
       in the original order, so the patterns and their instance lists come out
       exactly as before."""
    # 1. Extend every instance; drop duplicates, keeping first-seen order.
    extendedInstances = []
    seenKeys = set()
    for instance in pattern.instances:
        for newInstance in ExtendInstance(instance):
            key = InstanceKey(newInstance)
            if key not in seenKeys:
                seenKeys.add(key)
                extendedInstances.append(newInstance)
    # 2. Index the instances by signature (positions stay in list order).
    positionsBySignature = {}
    signatures = []
    for position, instance in enumerate(extendedInstances):
        signature = InstanceSignature(instance)
        signatures.append(signature)
        positionsBySignature.setdefault(signature, []).append(position)
    graphs = [None] * len(extendedInstances)
    def graphOf(position):
        if graphs[position] is None:
            graph = Graph.CreateGraphFromInstance(extendedInstances[position])
            if parameters.temporal:
                graph.TemporalOrder()
            graphs[position] = graph
        return graphs[position]
    # 3. Group: the earliest unassigned instance seeds a pattern and collects the
    #    later unassigned instances that match it and do not overlap.
    assigned = [False] * len(extendedInstances)
    newPatterns = []
    for seedPosition, seedInstance in enumerate(extendedInstances):
        if assigned[seedPosition]:
            continue
        assigned[seedPosition] = True
        seedGraph = graphOf(seedPosition)
        matchingInstances = [seedInstance]
        overlapIndex = OverlapIndex(parameters.overlap)
        overlapIndex.add(seedInstance)
        for position in positionsBySignature[signatures[seedPosition]]:
            if position <= seedPosition or assigned[position]:
                continue
            candidate = extendedInstances[position]
            if Graph.GraphMatch(seedGraph, graphOf(position)) and (not overlapIndex.overlaps(candidate)):
                matchingInstances.append(candidate)
                overlapIndex.add(candidate)
                assigned[position] = True
        graphs[seedPosition] = None # the seed graph now belongs to the pattern
        newPatterns.append(CreatePatternFromInstances(seedGraph, matchingInstances))
    return newPatterns

def ExtendInstance (instance):
    """Returns list of new instances created by extending the given instance by one new edge in all possible ways."""
    newInstances = []
    unusedEdges = OrderedSet([e for v in instance.vertices for e in v.edges]) - instance.edges
    for edge in unusedEdges:
        newInstance = ExtendInstanceByEdge(instance, edge)
        newInstances.append(newInstance)
    return newInstances

def ExtendInstanceByEdge(instance, edge):
    """Create and return new instance built from given instance and adding given edge and vertices of edge if new."""
    newInstance = Instance()
    newInstance.vertices = OrderedSet(instance.vertices)
    newInstance.edges = OrderedSet(instance.edges)
    newInstance.edges.add(edge)
    newInstance.vertices.add(edge.source)
    newInstance.vertices.add(edge.target)
    return newInstance

def InsertNewInstance(instanceList, newInstance):
    """Add newInstance to instanceList if it does not match an instance already on the list."""
    match = False
    for instance in instanceList:
        if (InstanceMatch(instance,newInstance)):
            match = True
            break
    if not match:
        instanceList.append(newInstance)

def InstanceMatch(instance1,instance2):
    """Return True if given instances match, i.e., contain the same vertex and edge object instances."""
    if (instance1.vertices == instance2.vertices) and (instance1.edges == instance2.edges):
        return True
    else:
        return False

def InstancesOverlap(overlap, instanceList, instance):
    """Returns True if instance overlaps with an instance in the given instanceList
    according to the overlap parameter, which indicates what type of overlap ignored.
    Overlap="none" means no overlap ignored. Overlap="vertex" means vertex overlap
    ignored. Overlap="edge" means vertex and edge overlap ignored, but the instances
    cannot be identical."""
    for instance2 in instanceList:
        if InstanceOverlap(overlap, instance, instance2):
            return True
    return False

def InstanceOverlap(overlap, instance1, instance2):
    """Returns True if given instances overlap according to given overlap parameter.
    See InstancesOverlap for explanation."""
    if overlap == "edge":
        return InstanceMatch(instance1, instance2)
    elif overlap == "vertex":
        return instance1.edges.intersect(instance2.edges)
    else: # overlap == "none"
        return instance1.vertices.intersect(instance2.vertices)


class OverlapIndex:
    """Answers "does this instance overlap any instance added so far?" in time
    proportional to the size of the instance, with the same meaning as
    InstancesOverlap(overlap, instanceList, instance):
      overlap == "none"   -> overlap means sharing a vertex
      overlap == "vertex" -> overlap means sharing an edge
      overlap == "edge"   -> overlap means being the identical instance"""

    def __init__(self, overlap):
        self.overlap = overlap
        self.seen = set()

    def _items(self, instance):
        if self.overlap == "edge":
            return [InstanceKey(instance)]
        if self.overlap == "vertex":
            return instance.edges.list_container
        return instance.vertices.list_container # overlap == "none"

    def add(self, instance):
        self.seen.update(self._items(instance))

    def overlaps(self, instance):
        for item in self._items(instance):
            if item in self.seen:
                return True
        return False


# ----- Pattern List Operations

def PatternListInsert(newPattern, patternList, maxLength, valueBased):
    """Insert newPattern into patternList. If newPattern is isomorphic to an existing pattern on patternList, then keep higher-valued
       pattern. The list is kept in decreasing order by pattern value. If valueBased=True, then maxLength represents the maximum number
       of different-valued patterns on the list; otherwise, maxLength represents the maximum number of patterns on the list.
       Assumes given patternList already conforms to maximums."""
    # Check if newPattern unique (i.e., non-isomorphic or isomorphic but better-valued)
    for pattern in patternList:
        if (Graph.GraphMatch(pattern.definition,newPattern.definition)):
            if (pattern.value >= newPattern.value):
                return # newPattern already on list with same or better value
            else:
                # newpattern isomorphic to existing pattern, but better valued
                patternList.remove(pattern)
                break
    # newPattern unique, so insert in order by value
    insertAtIndex = 0
    for pattern in patternList:
        if newPattern.value > pattern.value:
            break
        insertAtIndex += 1
    patternList.insert(insertAtIndex, newPattern)
    # check if patternList needs to be trimmed
    if valueBased:
        uniqueValues = UniqueValues(patternList)
        if len(uniqueValues) > maxLength:
            removeValue = uniqueValues[-1]
            while (patternList[-1].value == removeValue):
                patternList.pop(-1)
    else:
        if len(patternList) > maxLength:
            patternList.pop(-1)

def UniqueValues(patternList):
    """Returns list of unique values of patterns in given pattern list, in same order."""
    uniqueValues = []
    for pattern in patternList:
        if pattern.value not in uniqueValues:
            uniqueValues.append(pattern.value)
    return uniqueValues
