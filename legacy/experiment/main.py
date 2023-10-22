from __future__ import print_function
import sys
import xml.etree.ElementTree as ET
def printnode(name) :
    return str((int(name.replace("a","")) + 1))

output = open('data.dzn','w')
tree = ET.parse('farnush1-p.xml')

root = tree.getroot()
nodeNumber = 0
channelNumber = 0
node_list=[]
#To Count Number of ACTORS
for actor in root.iter('actor') :
    nodeNumber = nodeNumber + 1
    node_list.append(actor.attrib['name'])

#To Count Number of Channels
for channel in root.iter('channel') :
    if not (channel.attrib['srcActor'] == channel.attrib['dstActor']) :
        channelNumber = channelNumber + 1
###################################################################################
Adjancy_matrix = [['<>' for _ in range(nodeNumber)] for _ in range(nodeNumber)]


for channel in root.iter('channel') :
    src_actor_name = channel.attrib['srcActor']
    dst_actor_name = channel.attrib['dstActor']
    has_initial_tokens = 'initialTokens' in channel.attrib
    # Find the corresponding indices in the node_list
    src_index = node_list.index(src_actor_name)
    dst_index = node_list.index(dst_actor_name)
    # Update the adjacency matrix to indicate a connection
    if has_initial_tokens:
        initial_tokens = int(channel.get('initialTokens'))
        Adjancy_matrix[src_index][dst_index] = initial_tokens
    else:
        Adjancy_matrix[src_index][dst_index] = 0




matrix_str = "[|"
for row in Adjancy_matrix:
    matrix_str += ",".join(map(str, row))
    matrix_str += "|" + '\n'

matrix_str = matrix_str[:-1]  # Remove the last '|'

output.write("Arc = " + matrix_str + "]" + ";")

#############################################################################################
output.write('\n'+ "n = " + str(nodeNumber) + ';' + " \n")
exectimeStr = ""
for act in root.iter('actor') :
    edgedict = {}
    exectime = "0"
    for actprop in root.iter('actorProperties') :
        if act.attrib["name"] == actprop.attrib["actor"] :
            exectime = actprop[0][0].attrib['time']
    exectimeStr = exectimeStr + str(exectime) + ","
if exectimeStr.endswith(','):
    exectimeStr = exectimeStr[:-1]

output.write("T = [" + exectimeStr + "]" + ";" + "\n")

output.close()