import os
import sys

import networkx as nx

import re
import json
import string
from collections import Counter, namedtuple
from itertools import chain
from functools import reduce
from math import log

from lookup import ROMAN_TO_INT 

FILE_DIR = os.path.dirname(os.path.abspath(__file__))

PLAY_PATH = os.path.abspath(sys.argv[1])
PLAY_NAME = PLAY_PATH[:-5]

OUTPUT_PATH = PLAY_NAME + ".out"

"""
MODULE LEVEL MATCHERS
=====================

Included in the module are regex matchers which are throughout by functions in
the module.

Below are examples from Shakespeare's 'All's Well That Ends Well ' (in html)
that will be matched. 

DIALOGUE_MATCHER
----------------
<a name="1.1.11">[To HELENA]  The best wishes that can be forged in</a><br>

CHARACTER_MATCHER
-----------------
<a name="speech25"><b>BERTRAM</b></a>

STAGE_DIRECTION_MATCHER
-----------------------
<a name="speech25"><b>BERTRAM</b></a>

ACT_MATCHER
-----------
<h3>ACT I</h3>

SCENE_MATCHER
-------------
<h3>SCENE I. Rousillon. The COUNT's palace.</h3>
"""

DIALOGUE_PATTERN = r'^<a name="?(?P<act>\d)\.(?P<scene>\d)\.\d+"?>' \
    '(\[(?P<instruction>.*)\])?(?P<dialogue>.*)</a><br>'
DIALOGUE_MATCHER = re.compile(DIALOGUE_PATTERN, re.IGNORECASE)

CHARACTER_PATTERN = r'^<a name="?speech\d+"?><b>(?P<name>.*)</b></a>'
CHARACTER_MATCHER = re.compile(CHARACTER_PATTERN, re.IGNORECASE)

STAGE_DIRECTION_PATTERN = r'<i>(?P<stage_direction>.*)</i>'
STAGE_DIRECTION_MATCHER = re.compile(STAGE_DIRECTION_PATTERN, re.IGNORECASE)

INSTRUCTION_PATTERN = r're-enter|enter|exit|exeunt|aside|read|to'
INSTRUCTION_MATCHER = re.compile(
        INSTRUCTION_PATTERN,
        re.IGNORECASE
        )

ACT_PATTERN = r"<h3>act (?P<act>[IVX]+).*</h3>"
ACT_MATCHER = re.compile(ACT_PATTERN, re.IGNORECASE)

SCENE_PATTERN = r"<h3>scene (?P<scene>[IVX]+).*</h3>"
SCENE_MATCHER = re.compile(SCENE_PATTERN, re.IGNORECASE)

class Dialogue(namedtuple('Dialogue', [
        'dialogue', 
        'instruction', 
        'character',
        'act',
        'scene'
        ])):
    TYPE = 'dialogue'
    def __repr__(self):
        return str(self.act) + '.' + str(self.scene) + ' :' \
               + str(self.dialogue) + ' : ' + str(self.instruction)

class Character(namedtuple('Character', ['character'])):
    TYPE = 'character'
    def __repr__(self):
        return self.character

class Instruction(namedtuple('Instruction', [
    'raw', 
    'actions', 
    'characters',
    'default_character'
    ])):
    TYPE = 'instruction'
    def __repr__(self):
        action_characters = [ 
                str(self.actions[i]) + " - " + str(self.characters[i])
                for i in range(len(self.actions)) ]
        return self.raw + ' : ' + str(action_characters) \
                + ' : ' + str(self.default_character)

class Act(namedtuple('Act', ['act'])):
    TYPE ='act'
    def __repr____(self):
        return self.act

class Scene(namedtuple('Scene', ['scene'])):
    TYPE ='scene'
    def __repr____(self):
        return self.scene

def get_speaking_characters(play_lines):
    """ return a set of all character names """
    return { matched_line.group('name').upper() for matched_line in
            (CHARACTER_MATCHER.search(line) for line in play_lines)
            if matched_line }

def get_known_character_matcher(speaking_characters):
    joined_characters = "|".join(speaking_characters)
    characters_pattern = "(?P<character>" + joined_characters + ")"
    known_characters_matcher = re.compile(
            characters_pattern,
            re.IGNORECASE)
    return known_characters_matcher

def parse_raw_text(raw_play_lines, speaking_characters):
    """ Parse the lines of the play which is in HTML

    Each line is either ignored or putting into a class derived from a
    namedtuple. 
    
    Notes
    -----

    character_chain 
        A list of the characters who speak in turn, all capitalized

    Example:
        >>> PLAY_NAME
        alls_well_that_ends_well
        >>> character_chain
        ['COUNTESS', 'BERTRAM', 'LAFEU', 'COUNTESS', 'BERTRAM', ...]
    """
    known_characters_matcher = get_known_character_matcher(speaking_characters)
    parsed_lines = []
    character_chain = []
    for i, line in enumerate(raw_play_lines):
        d_match = DIALOGUE_MATCHER.search(line)
        # d has 3-4 groups : act, scene, dialogue, optional instruction
        if d_match:
            dialogue = Dialogue(
                    d_match.group('dialogue'), 
                    process_instructions(
                        d_match.group('instruction'),
                        known_characters_matcher,
                        character_chain[-1]),
                    character_chain[-1],
                    d_match.group('act'), 
                    d_match.group('scene'))
            parsed_lines.append(dialogue)
            continue
        c_match = CHARACTER_MATCHER.search(line)
        if c_match:
            name = c_match.group('name').upper()
            character_chain.append(name)
            parsed_lines.append(Character(name))
            continue
        sd_match = STAGE_DIRECTION_MATCHER.search(line)
        if sd_match:
            stage_direction = sd_match.group('stage_direction')
            prev_character = character_chain[-1] if character_chain else None
            instruction = process_instructions(
                    stage_direction,
                    known_characters_matcher,
                    prev_character)
            parsed_lines.append(instruction)
            continue
        act_match = ACT_MATCHER.search(line)
        if act_match:
            act_roman = act_match.group('act')
            act = ROMAN_TO_INT[act_roman]
            parsed_lines.append(Act(act))
            prev_character = None
            continue
        scene_match = SCENE_MATCHER.search(line)
        if scene_match:
            scene_roman = scene_match.group('scene')
            scene = ROMAN_TO_INT[scene_roman]
            parsed_lines.append(Scene(scene))
            prev_character = None
            continue
    return parsed_lines

def process_instructions(
        instruction, 
        known_characters_matcher, 
        default_character):
    """
    For each sentence only one action (the first) is matched, but a single
    instruction can contain multiple sentences, which is why action are
    returned as a list. Each action can be applied to multiple characters. Note
    that all character names are shifted to uppercase
    """
    if instruction is None:
        return None
    instruction_lines = instruction.split(".")
    actions = [ match.group(0) if match else None for match in 
            ( INSTRUCTION_MATCHER.search(line) 
                for line in instruction_lines ) ]
    characters = [ 
            [ character.upper() 
                for character in known_characters]
            for known_characters in
            ( known_characters_matcher.findall(line) 
                for line in instruction_lines) ]
    return Instruction(instruction, actions, characters, default_character)

def get_act_scene_range(play_lines):
    """
    Returns
    -------
    act_scenes
        list of tuples containing (act, scene)

        >>> PLAY_NAME
        alls_well_that_ends_well
        >>> act_scenes
        [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), ...]

    act_scene_range
        contains start of all act/scenes as well as the index of the last line
        + 1 (so basically len(play_lines) appended)
    """
    act_scenes = []
    act_scene_range = []
    for i, line in enumerate(play_lines):
        if line.TYPE == Scene.TYPE:
            prev_line = play_lines[i - 1]
            if prev_line.TYPE == Act.TYPE:
                act_scenes.append((prev_line.act, line.scene))
                act_scene_range.append(i - 1)
            else:
                act_scenes.append((
                    act_scenes[-1][0] if act_scenes else 1,
                    line.scene))
                act_scene_range.append(i)
    act_scene_range.append(len(play_lines))
    # make sure that the beginning is part of an act, scene
    assert act_scene_range[0] == 0
    assert len(act_scenes) + 1 == len(act_scene_range)
    return act_scenes, act_scene_range

def get_entrance_exit(play_lines, act_scene_start_end):
    """
    For each character in the play, entrance[character] gives the line
    numbers, of `play_lines`, for when they enter a scene. exit[character] does
    the same for when the characters exit
    """
    entrance_exit = [ 
            entrance_exit_by_scene(play_lines, scene_start, scene_end)
            for scene_start, scene_end in act_scene_start_end ]
    entrance, exit = map(list, zip(*entrance_exit))
    return entrance, exit

def entrance_exit_by_scene(play_lines, scene_start, scene_end):
    """ 
    Note
    ----
    If character enters, exit and re-enters, scene_entrance will note only
    first entrance; scene_exit will note only first exit.

    scene_exit gives the last line for each character inclusive.
    """
    scene_entrance = dict()
    scene_exit = dict()
    character_start = create_check_and_add(scene_entrance, scene_start)
    character_end = create_check_and_add(
            scene_exit, 
            scene_end, 
            entering=False)
    for i in range(scene_start, scene_end):
        line = play_lines[i]
        character_start(line, i)
    for i in reversed(range(scene_start, scene_end)):
        line = play_lines[i]
        character_end(line, i)
    # ensure that characters have both entrance and exit
    close_loose_characters(scene_entrance, scene_exit, scene_end - 1)
    close_loose_characters(scene_exit, scene_entrance, scene_start)
    return scene_entrance, scene_exit

def close_loose_characters(characters_one, characters_two, default_line_number):
    for character in (characters_one.keys() - characters_two.keys()):
        characters_two[character] = default_line_number

def create_check_and_add(scene, default, entering=True):
    add_if_not_in = create_add_if_not_in(scene)
    patterns = ['enter'] if entering else ['exit', 'exeunt']
    def check_and_add(line, i):
        if line.TYPE == Character.TYPE:
            add_if_not_in(line.character, default)
        elif line.TYPE == Instruction.TYPE:
            instruction_character_start(
                    line, 
                    i, 
                    patterns,
                    add_if_not_in
                    )
        elif line.TYPE == Dialogue.TYPE:
            add_if_not_in(line.character, default)
            instruction = line.instruction
            if instruction:
                instruction_character_start(
                        instruction, 
                        i, 
                        patterns,
                        add_if_not_in
                        )
    return check_and_add

def instruction_character_start(
        instruction, 
        line_index, 
        patterns, 
        add_if_not_in):
    """ 
    determine if instruction contains enter/exit type action and add_if_not_in
    either default_character or characters in instruction
    """
    for i, action in enumerate(instruction.actions):
        if pattern_in(patterns, action):
            if not instruction.characters[i]:
                if instruction.default_character:
                    add_if_not_in(instruction.default_character, line_index)
            for character in instruction.characters[i]:
                add_if_not_in(character, line_index)

def create_add_if_not_in(scene_characters):
    def add_if_not_in(character, i):
        if character not in scene_characters:
            scene_characters[character] = i
    return add_if_not_in

def pattern_in(patterns, action):
    return action and any(pattern in action.lower() for pattern in patterns)

def get_presence(
        speaking_characters, 
        play_lines, 
        act_scene_start_end, 
        entrance, 
        exit):
    adj = { character : dict() for character in speaking_characters }
    for i, start_end in enumerate(act_scene_start_end):
        get_presence_by_scene(
                adj, 
                play_lines, 
                start_end, 
                entrance[i], 
                exit[i])
    return adj

def get_presence_by_scene(
        adj, 
        play_lines, 
        start_end, 
        scene_entrance, 
        scene_exit):
    scene_start, scene_end = start_end
    characters_present = set()
    inv_entrance, inv_exit = map(invert_dict, [scene_entrance, scene_exit])
    for i in range(scene_start, scene_end):
        line = play_lines[i]
        if i in inv_entrance:
            for character in inv_entrance[i]:
                characters_present.add(character)
        if line.TYPE == Dialogue.TYPE:
            for character in characters_present - {line.character}:
                if character in adj[line.character]:
                    adj[line.character][character] += 1
                else:
                    adj[line.character][character] = 1
        if i in inv_exit:
            for character in inv_exit[i]:
                characters_present.remove(character)

def invert_dict(front_dict):
    """ Take a dict of key->values and return values->[keys] """
    back_dict = { value : [] for value in front_dict.values() }
    for key, value in front_dict.items():
        back_dict[value].append(key)
    return back_dict
    
def preprocess(raw_play_lines):
    speaking_characters = get_speaking_characters(raw_play_lines)
    play_lines = parse_raw_text(raw_play_lines, speaking_characters)
    return speaking_characters, play_lines

def process(speaking_characters, play_lines):
    act_scenes, act_scene_range = get_act_scene_range(play_lines)
    act_scene_start_end = list(zip(act_scene_range, act_scene_range[1:]))
    entrance, exit = get_entrance_exit(
            play_lines, 
            act_scene_start_end)
    adj = get_presence(
            speaking_characters, 
            play_lines, 
            act_scene_start_end,
            entrance, 
            exit)
    return adj

def postprocess(play_lines, speaking_characters, adj, gender):
    graph = create_graph(adj)
    reciprocal_graph = create_graph(adj, reciprocal=True)
    characters_by_importance = get_characters_by_importance(
            play_lines, 
            speaking_characters, 
            graph,
            reciprocal_graph)
    vocab_difference(play_lines, gender)
    bechdel_test(play_lines, characters_by_importance, adj, gender)
    return graph

def get_characters_by_importance(
        play_lines, 
        speaking_characters, 
        graph,
        reciprocal_graph):
    reverse_graph = graph.reverse(copy=True)

    # METRICS
    lines_by_character = get_lines_by_character(play_lines, speaking_characters)
    out_degree = nx.out_degree_centrality(graph)
    page_rank = nx.pagerank_numpy(reverse_graph)
    betweenness = nx.betweenness_centrality(reciprocal_graph)

    metrics = [lines_by_character, out_degree, page_rank, betweenness]
    relative_importance = [0.625, 0.125, 0.125, 0.125]

    for i, x in enumerate(metrics):
        normalize_linear(x)
        scale(x, relative_importance[i])

    character_value = { character : sum( metric[character] for metric in metrics )
            for character in speaking_characters }
    sorted_characters = dict_sorted(character_value)
    return sorted_characters

def scale(x, a):
    for key in x:
        x[key] *= a

def get_lines_by_character(play_lines, speaking_characters):
    lines_by_character = { key : 0 for key in speaking_characters }
    for line in play_lines:
        if line.TYPE == Dialogue.TYPE:
            lines_by_character[line.character] += 1
    return lines_by_character

def normalize_linear(x):
    biggest = max(x.values())
    scale(x, 1/biggest)

def dict_sorted(x):
    return sorted(( (key , x[key]) for key in x ), key=lambda x: x[1])

def process_play(raw_play_lines, gender):
    speaking_characters, play_lines = preprocess(raw_play_lines)
    adj = process(speaking_characters, play_lines)
    graph = postprocess(play_lines, speaking_characters, adj, gender)
    return play_lines, graph

# NETWORKX AND PYGRAPHVIZ

def create_graph(adj, reciprocal=False):
    def reciprocal_weight(speaker, recipient):
        weight = adj[speaker][recipient]
        try:
            reciprocal_weight = 1 / weight
            return reciprocal_weight
        except ZeroDivisionError:
            return float('inf')
    def normal_weight(speaker, recipient):
        return adj[speaker][recipient]
    weight_f = reciprocal_weight if reciprocal else normal_weight
    edges = [ (
        speaker, 
        recipient, 
        {'weight' : weight_f(speaker, recipient), 'color' : 'blue'}
        ) 
            for speaker in adj
            for recipient in adj[speaker] ]
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    return graph

# Bechdel Test

""" 
The Bechdel test is defined as follows. It 'asks whether a work of fiction
features at least two women who talk to each other about something other than a
man. The requirement that the two women must be named is sometimes added.' 

For this implementation the requirement that the conversation involve something
other than a man is fufilled by the following

1. In a scene the women must not mention any other male characters by name.  2.
they must not mention any of the following words relating to male partners.

['boyfriend', 'partner', 'husband', 'spouse', 'lover', 'admirer', 'fiancé',
'amour', 'inamorato']

3. they must not mention any of the following words related to sexual
relationships

['sex', 'sexual', 'intercourse', 'marriage', 'matrimony','courting', 'love',
'wedlock']

In place of whether the two women are named, both women must be in the upper
50% of characters as given by character by importance.  
"""

def bechdel_test(play_lines, characters_by_importance, adj, gender):
    print(gender)
    print(characters_by_importance)
    # print(play_lines, characters_by_importance, adj, gender, sep='\n')
    # if odd number of characters, includes n + 1 characters, where
    # len(characters) = 2n + 1
    start = len(characters_by_importance) // 2
    notable_females = [ character for character in (x[0] for x in
        characters_by_importance[start:]) if gender[character] == "F"]
    print(notable_females)

# VOCAB DIFFERENCES

def vocab_difference(play_lines, gender):
    males_vocab = dict()
    female_vocab = dict()
    line_to_vocab = create_line_to_vocab()
    for line in play_lines:
        if line.TYPE == Dialogue.TYPE:
            gender_character = gender[line.character]
            if gender_character == "M":
                line_to_vocab(line.dialogue, males_vocab)
            elif gender_character == "F":
                line_to_vocab(line.dialogue, female_vocab)
    get_word_gender = create_get_word_gender(males_vocab, female_vocab)
    word_gender = { key : get_word_gender(key)
            for key in set(males_vocab.keys()).union(set(female_vocab.keys())) }
    word_gender_sorted = sorted(word_gender, key=lambda x: word_gender[x])

    # print([ (word, word_gender[word]) for word in word_gender_sorted[:25] ])
    # print([ (word, word_gender[word]) for word in word_gender_sorted[-25:] ])
    # print(word_gender_sorted[:25])
    # print(word_gender_sorted[-25:])

def create_line_to_vocab():
    remove_punctuation = create_remove_punctuation()
    def line_to_vocab(line, vocab):
        stripped = remove_punctuation(line)
        words = stripped.split(" ")
        for word in words:
            if word in vocab:
                vocab[word] += 1
            else:
                vocab[word] = 1
    return line_to_vocab

def create_get_word_gender(males_vocab, female_vocab):
    num_male_words = sum(males_vocab.values())
    num_female_words = sum(female_vocab.values())
    male_threshold = num_male_words / len(males_vocab)
    female_threshold = num_female_words / len(female_vocab)
    print(male_threshold)
    print(female_threshold)
    def get_ratio(m_num, f_num):
        norm_m_num = m_num / num_male_words
        norm_f_num = f_num / num_female_words
        diff = norm_m_num - norm_f_num
        _sum = norm_m_num + norm_f_num
        ratio = diff / _sum
        return ratio
    def get_word_gender(word):
        m_num = males_vocab.get(word, 0)
        f_num = female_vocab.get(word, 0)
        meet_threshold = m_num > male_threshold or f_num > female_threshold 
        metric = get_ratio(m_num, f_num) if meet_threshold else 0
        return metric
    return get_word_gender
    


def create_remove_punctuation():
    remove_punct_map = dict.fromkeys(map(ord, string.punctuation))
    print(remove_punct_map)
    def remove_punctuation(line):
        return line.translate(remove_punct_map)
    return remove_punctuation

# INPUT OUTPUT

def to_output(parsed_play):
    play_lines, graph = parsed_play
    a = [ str(x) + "\n" for x in play_lines ]
    list_to_file(a, OUTPUT_PATH)
    print("writing to ", OUTPUT_PATH)
    dot_graph = nx.nx_agraph.to_agraph(graph)
    dot_graph.write(PLAY_NAME + ".dot")
    prog = ['dot', 'circo']
    for p in prog:
        dot_graph.layout(p)
        dot_graph.draw(PLAY_NAME + "_" + p + ".png")

def file_to_list(path):
    with open(path, 'r') as inputFile:
        return inputFile.readlines()

def json_file_to_dict(path):
    with open(path, 'r') as jsonFile:
        return json.load(jsonFile)

def to_json(x, path):
    with open(path, 'w') as jsonFile:
        json.dump(x, jsonFile)

def list_to_file(li, path):
    with open(path, 'w') as outputFile:
        outputFile.writelines(li)

def get_files():
    play_lines_raw = file_to_list(PLAY_PATH)
    try:
        gender = json_file_to_dict(PLAY_NAME + "_gender.json")
    except FileNotFoundError:
        print("require gender file")
        gender = None
    return play_lines_raw, gender

def main():
    play_lines, gender = get_files()
    output = process_play(play_lines, gender)
    # to_output(output)

if __name__ == "__main__":
    main()
