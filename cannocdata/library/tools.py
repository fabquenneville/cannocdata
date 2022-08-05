#!/usr/bin/env python3
'''
    These are various tools used by mediacurator
'''

import copy
import configparser
import os
import sys
import csv
import re
import chardet
import shutil
import json
import requests
import uuid
import time
# from googletrans import Translator, constants
# from google_trans_new import google_translator
# from translate import Translator
# import goslate
import argostranslate.package
import argostranslate.translate
from difflib import SequenceMatcher


def load_arguments():
    '''Get/load command parameters

    Args:

    Returns:
        arguments: A dictionary of lists of the options passed by the user
    '''
    arguments = {
        "id": None,
        "task": None,
        "translator": None,
        "lang_from": None,
        "lang_to": None,
        "keys_from": [],
        "keys_to": [],
        "source": None,
        "sources": [],
        "destination": None,
    }

    for arg in sys.argv:
        if "-id:" in arg:
            arguments["id"] = arg[4:]
        elif "-task:" in arg:
            arguments["task"] = arg[6:]
        elif "-translator:" in arg:
            arguments["translator"] = arg[12:]
        elif "-lang_from:" in arg:
            arguments["lang_from"] = arg[11:]
        elif "-lang_to:" in arg:
            arguments["lang_to"] = arg[9:]
        elif "-keys_from:" in arg:
            arguments["keys_from"] += arg[11:].split(",")
        elif "-keys_to:" in arg:
            arguments["keys_to"] += arg[9:].split(",")
        elif "-source:" in arg:
            arguments["source"] = arg[8:]
        elif "-sources:" in arg:
            arguments["sources"] += arg[9:].split(",")
        elif "-destination:" in arg:
            arguments["destination"] = arg[13:]

    return arguments


def get_parent(filepath, level=1):
    if level < 1:
        return os.path.dirname(filepath)
    return get_parent(os.path.dirname(filepath), level - 1)


def find_in_parents(file):
    if not os.path.exists(file):
        for x in range(3):
            tmpfile = os.path.join(get_parent(__file__, x), file)
            if os.path.exists(tmpfile):
                file = tmpfile
    if not os.path.exists(file):
        return False
    return os.path.abspath(file)


def load_config(file="config.ini"):
    '''

    Args:
        file: The config filename

    Returns:
        config: The parsed configuration
    '''
    config = configparser.ConfigParser()
    if find_in_parents(file):
        file = find_in_parents(file)
    config.read(file)
    return config._sections


def init_argos(from_code, to_code):
    available_packages = argostranslate.package.get_available_packages()
    available_package = list(
        filter(lambda x: x.from_code == from_code and x.to_code == to_code,
               available_packages))[0]
    download_path = available_package.download()
    argostranslate.package.install_from_path(download_path)
    installed_languages = argostranslate.translate.get_installed_languages()
    from_lang = list(filter(lambda x: x.code == from_code,
                            installed_languages))[0]
    to_lang = list(filter(lambda x: x.code == to_code, installed_languages))[0]
    return from_lang.get_translation(to_lang)


def diclist_to_csv(diclist, destination, encoding='utf-8'):
    keys = diclist[0].keys()
    with open(destination, 'w', newline="", encoding=encoding) as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(diclist)


def translate_csv_argos(csv_raw, lang_from='en', lang_to='fr', keys={}):
    csv_translated = []
    translator = init_argos(lang_from, lang_to)
    for data in csv_raw:
        for k_from, k_to in keys.items():
            if k_from in data:
                data[k_to] = translator.translate(data[k_from])
        csv_translated.append(data)
    return csv_translated


def translate_azure(text, lang_from='en', lang_to='fr', config=load_config()):
    if 'azure' not in config:
        return False
    endpoint = config['azure']['endpoint']
    constructed_url = f"{endpoint}/translate?api-version=3.0&from={lang_from}&to={lang_to}"

    headers = {
        'Ocp-Apim-Subscription-Key': config['azure']['subscription'],
        'Ocp-Apim-Subscription-Region': config['azure']['region'],
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }
    body = [{'text': text}]
    try:
        request = requests.post(constructed_url, headers=headers, json=body)
        response = request.json()
        if "error" in response:
            print("Error with Azure api:")
            print(f"Code: {response['error']['code']}")
            print(f"Message: {response['error']['message']}")
            exit()
        return response[0]['translations'][0]['text']
    except requests.exceptions.ConnectionError:
        print("ConnectionError: waiting 5 seconds and trying again.")
        time.sleep(5)
        return translate_azure(text, lang_from, lang_to, config)

def translate(text,
              lang_from='en',
              lang_to='fr',
              translator="argos",
              engine=None):
    if translator == 'azure':
        return translate_azure(text, lang_from, lang_to)
    else:
        if not engine:
            engine = init_argos(lang_from, lang_to)
        return engine.translate(text)


def translate_csv_azure(csv_raw, lang_from='en', lang_to='fr', keys={}):
    csv_translated = []
    for data in csv_raw:
        for k_from, k_to in keys.items():
            if k_from in data:
                data[k_to] = translate_azure(data[k_from], lang_from, lang_to)

        csv_translated.append(data)
    return csv_translated


def translate_csv(source=None,
                  destination=None,
                  lang_from=None,
                  lang_to="en",
                  keys={},
                  translator="argos"):
    arguments = load_arguments()

    if arguments['source']:
        source = arguments['source']
    if not source:
        return False

    if not destination:
        destination = source

    if arguments['lang_from']:
        lang_from = arguments['lang_from']
    if arguments['lang_to']:
        lang_from = arguments['lang_to']
    if not lang_from:
        return False  # TODO detect language

    if arguments["keys_from"] and arguments["keys_to"]:
        keys = {}
        if len(arguments["keys_from"]) == len(arguments["keys_to"]):
            for i in range(len(arguments["keys_from"])):
                keys[arguments["keys_from"][i]] = arguments["keys_to"][i]
    if not keys:
        return False

    if not os.path.isfile(source):
        return False

    encoding = get_encoding_type(source).lower()
    csv_raw = csv.DictReader(open(source, encoding=encoding))
    if translator == 'azure':
        csv_translated = translate_csv_azure(csv_raw, lang_from, lang_to, keys)
    else:
        csv_translated = translate_csv_argos(csv_raw, lang_from, lang_to, keys)

    try:
        diclist_to_csv(csv_translated, destination, encoding)
    except UnicodeEncodeError:
        diclist_to_csv(csv_translated, destination)


def combine_csvs_lfl(sources, destination):
    if not sources:
        return False
    if not destination:
        return False
    encoding = 'utf-8'
    combined_csv = []
    for source in sources:
        if os.path.isfile(source):
            encoding = get_encoding_type(source).lower()
            csv_items = list(csv.DictReader(open(source, encoding=encoding)))
            for i in range(len(csv_items)):
                if i >= len(combined_csv):
                    combined_csv.append(csv_items[i])
                else:
                    for k, v in csv_items[i].items():
                        combined_csv[i][k] = v
    return combined_csv, encoding


def combine_csvs_id(sources, id):
    if not sources:
        return False
    encoding = 'utf-8'
    combined_csv = {}
    for source in sources:
        if os.path.isfile(source):
            encoding = get_encoding_type(source).lower()
            csv_items = csv.DictReader(open(source, encoding=encoding))
            for csv_item in csv_items:
                if not id in csv_item:
                    break
                if not csv_item[id] in combined_csv:
                    combined_csv[csv_item[id]] = csv_item
                else:
                    combined_csv[csv_item[id]] |= csv_item
    return list(combined_csv.values()), encoding


def get_eleclasses():
    return {
        "Exemple(s) illustratif(s)": "Illustrative example(s)",
        "Tous les exemples": "All examples",
        "Inclusion(s)": "Inclusion(s)",
        "Exclusion(s)": "Exclusion(s)",
        "Fonctions principales": "Main duties",
        "Conditions d'accès à la profession":
        "Employment requirements",
        "Renseignements supplémentaires": "Additional information"
    }

def combine_csvs_translate(csv_en, csv_fr, key_en, key_fr, key_match):
    if not csv_en or not csv_fr:
        return False
    elemclasses = get_eleclasses()
    encoding = 'utf-8'
    combined_csv = []

    if os.path.isfile(csv_en):
        encoding = get_encoding_type(csv_en).lower()
        combined_csv = list(csv.DictReader(open(csv_en, encoding=encoding)))

    for i in range(len(combined_csv)):
        combined_csv[i] = {
            "noc_code": None,
            "type_english": None,
            "name_english": None,
            "type_french": None,
            "name_french": None,
        } | combined_csv[i]

    if os.path.isfile(csv_fr):
        argos = init_argos("fr", "en")
        encoding = get_encoding_type(csv_fr).lower()
        csv_items = csv.DictReader(open(csv_fr, encoding=encoding))
        # count = 1
        for line in csv_items:
            best_matches = {}
            needle = {
                "noc_code": line['noc_code'],
                "type_english": elemclasses[line['type_french']],
                "name_english": None,
                "type_french": None,
                "name_french": None,
            }
            translator = "argos"
            needle["name_english"] = translate(line['name_french'], "fr", "en",
                                               translator, argos)
            found = False


            i, p = loopfind(needle, combined_csv, "name_english")
            if isinstance(i, (int, float)) and p == 1:
                found = True
                combined_csv[i]['type_french'] = line['type_french']
                combined_csv[i]['name_french'] = line['name_french']
            elif isinstance(i, (int, float)) and p:
                best_matches[translator] = {
                    "i": i,
                    "p": p,
                    "name_english": needle["name_english"]
                }

            if not found:
                translator = "azure"
                needle["name_english"] = translate(line['name_french'], "fr",
                                                   "en", translator)
                i, p = loopfind(needle, combined_csv, "name_english")
                if isinstance(i, (int, float)) and p == 1:
                    found = True
                    combined_csv[i]['type_french'] = line['type_french']
                    combined_csv[i]['name_french'] = line['name_french']
                elif isinstance(i, (int, float)) and p:
                    best_matches[translator] = {
                        "i": i,
                        "p": p,
                        "name_english": needle["name_english"]
                    }

            if not found and len(best_matches) > 0:
                found = True
                high_p = 0
                high_i = 0
                high_translator = None
                for translator, namedata in best_matches.items():
                    if namedata["p"] > high_p:
                        high_p = namedata["p"]
                        high_i = namedata["i"]
                        high_translator = translator
                combined_csv[high_i]['type_french'] = line['type_french']
                combined_csv[high_i]['name_french'] = line['name_french']
            
            if not found:
                combined_csv.append({
                    "noc_code": line['noc_code'],
                    "type_english": elemclasses[line['type_french']],
                    "name_english": needle["name_english"],
                    "type_french": line['type_french'],
                    "name_french": line['name_french'],
                })

            # if count > 100:
            #     print(json.dumps(combined_csv, indent=4))
            #     exit()
            # count += 1
    # print(combined_csv)
    # print(json.dumps(combined_csv, indent=4))
    # exit()

    for i in range(len(combined_csv)):
        if not combined_csv[i]["type_french"]:
            for k, v in elemclasses.items():
                if v == combined_csv[i]["type_english"]:
                    combined_csv[i]["type_french"] = k
        
        if not combined_csv[i]["name_french"]:
            combined_csv[i]["name_french"] = translate(combined_csv[i]["name_english"], translator = "azure")

    return combined_csv, encoding


def compare_columns(source=None, keys_from={}, keys_to={}):
    return False


def combine_csvs(sources, destination, id=None):
    if not sources:
        return False
    if not destination:
        return False

    encoding = 'utf-8'
    combined_csv = None
    if not id:
        combined_csv, encoding = combine_csvs_lfl(sources, destination)
    else:
        combined_csv, encoding = combine_csvs_id(sources, destination, id)

    if combined_csv:
        diclist_to_csv(combined_csv, destination, encoding)


def print_csv(filepath):
    '''

    Args:
        filepath: the filepath of the csv

    Returns:
        False: Failed operation
    '''
    if not os.path.isfile(filepath):
        return False

    csv_raw = csv.DictReader(
        open(filepath, encoding=get_encoding_type(filepath).lower()))
    for row in csv_raw:
        print(row)


def print_longest(path):
    if os.path.isdir(path):
        for filename in os.listdir(path):
            if filename.endswith('.csv'):
                print_longest(os.path.join(path, filename))
    else:
        if not os.path.isfile(path):
            return False
        csv_raw = csv.DictReader(
            open(path, encoding=get_encoding_type(path).lower()))
        longest_key = 0
        longests = {}

        for row in csv_raw:
            for k, v in row.items():
                klen = len(k)
                if klen > longest_key:
                    longest_key = klen

                vlen = len(v)
                if k not in longests:
                    longests[k] = vlen
                elif vlen > longests[k]:
                    longests[k] = vlen

        longest_key += 5
        t1 = "Column"
        t2 = "Length"
        print(f"Longuest values in {path}:")
        print(f"{t1:{longest_key}} | {t2}")
        for k, v in longests.items():
            print(f"{k:{longest_key}} | {v}")
        print()


def get_encoding_type(filepath=None, bytearr=None):
    if filepath and os.path.exists(filepath):
        with open(filepath, 'rb') as file:
            return chardet.detect(file.read())['encoding']
    elif bytearr:
        chardet.detect(bytearr)['encoding']


def transcode(source, destination=None, destination_codec='utf-8'):
    '''

    Args:
        source      : The source filepath
        destination : The destination filepath

    Returns:
    '''
    if os.path.isdir(source):
        for filename in os.listdir(source):
            if filename.endswith('.csv'):
                transcode(os.path.join(source, filename), destination)
    else:
        if not destination:
            destination = source
        print(f"Transcoding to utf-8: {source}")
        document = open(source,
                        mode='r',
                        encoding=get_encoding_type(source).lower()).read()
        document = document.encode(encoding=destination_codec, errors='strict')
        document = document.decode(encoding=destination_codec, errors='strict')
        document = document.replace(u"\u00a0", " ")
        open(destination, mode='w', encoding=destination_codec).write(document)


def move_all_files(source, destination):
    '''

    Args:
        source      : The source filepath
        destination : The destination filepath

    Returns:
    '''
    for file_name in os.listdir(source):
        file_from = os.path.join(source, file_name)
        file_to = os.path.join(destination, file_name)
        if os.path.isfile(file_from):
            shutil.move(file_from, file_to)
            print('Moved:', file_name)


def test01(sources, destination, id=None):
    if not sources:
        return False
    if not destination:
        return False

    encoding = 'utf-8'
    combined_csv = None
    if not sources:
        return False
    if not destination:
        return False
    encoding = 'utf-8'
    combined_csv = {}
    for source in sources:
        if os.path.isfile(source):
            encoding = get_encoding_type(source).lower()
            csv_items = csv.DictReader(open(source, encoding=encoding))
            for csv_item in csv_items:
                # print(csv_item)
                # exit()
                if not id in csv_item:
                    break
                if not csv_item[id] in combined_csv:
                    combined_csv[csv_item[id]] = csv_item
                else:
                    combined_csv[csv_item[id]] |= csv_item

    # combined_csv = list(combined_csv.values())
    # if combined_csv:
    #     diclist_to_csv(combined_csv, destination, encoding)


def fill_missing(source, destination):
    if not source:
        return False
    if not destination:
        return False

    encoding = get_encoding_type(source).lower()
    csv_items = list(csv.DictReader(open(source, encoding=encoding)))
    elemclasses = get_eleclasses()

    for i in range(len(csv_items)):
        if not csv_items[i]["type_french"]:
            for k, v in elemclasses.items():
                if v == csv_items[i]["type_english"]:
                    csv_items[i]["type_french"] = k
        
        if not csv_items[i]["name_french"]:
            csv_items[i]["name_french"] = translate(csv_items[i]["name_english"], translator = "azure")
    
    diclist_to_csv(csv_items, destination, encoding)


def export(source, destination, id=None):
    if not os.path.isdir(os.path.join(destination, "elements")):
        os.makedirs(os.path.join(destination, "elements"))
    csvspaths = {
        "elem_fr":
        os.path.join(source, "cnp_2021_version_1.0_-_elements.csv"),
        "cls_fr":
        os.path.join(
            source,
            "cnp_2021_version_1.0_-_structure_de_la_classification.csv"),
        "elem_en":
        os.path.join(source, "noc_2021_version_1.0_-_elements.csv"),
        "cls_en":
        os.path.join(source,
                     "noc_2021_version_1.0_-_classification_structure.csv"),
    }

    csvs = {}
    for k in csvspaths.keys():
        encoding = get_encoding_type(csvspaths[k]).lower()
        csvs[k] = csv.DictReader(open(csvspaths[k], encoding=encoding))
        allitems = []
        lang = "en"
        filename = "elements"
        classified = {
            "illustratives": [],
            "exemples": [],
            "inclusions": [],
            "exclusions": [],
            "duties": [],
            "requirements": [],
            "other": [],
        }

        if k == "elem_en":
            for line in csvs[k]:
                newitem = {
                    "noc_code": line["Code - NOC 2021 V1.0"].strip(),
                    "name_english":
                    line["Element Description English"].strip(),
                }

                if line["Element Type Label English"] == "Illustrative example(s)":
                    classified["illustratives"].append(newitem)
                if line["Element Type Label English"] == "All examples":
                    classified["exemples"].append(newitem)
                if line["Element Type Label English"] == "Inclusion(s)":
                    classified["inclusions"].append(newitem)
                if line["Element Type Label English"] == "Exclusion(s)":
                    classified["exclusions"].append(newitem)
                if line["Element Type Label English"] == "Main duties":
                    classified["duties"].append(newitem)
                if line["Element Type Label English"] == "Employment requirements":
                    classified["requirements"].append(newitem)
                if line["Element Type Label English"] == "Additional information":
                    classified["other"].append(newitem)

                newitem = copy.deepcopy(newitem)
                newitem["type_english"] = line[
                    "Element Type Label English"].strip()
                allitems.append(newitem)

            for ke, va in classified.items():
                diclist_to_csv(
                    va,
                    os.path.join(destination, "elements", f"{ke}_{lang}.csv"),
                    encoding)

        elif k == "elem_fr":
            lang = "fr"
            for line in csvs[k]:
                newitem = {
                    "noc_code": line["Code de la CNP v1.0"].strip(),
                    "name_french":
                    line["Description d’élément Français"].strip(),
                }

                if line["Nom du type d’élément Français"] == "Exemple(s) illustratif(s)":
                    classified["illustratives"].append(newitem)
                if line["Nom du type d’élément Français"] == "Tous les exemples":
                    classified["exemples"].append(newitem)
                if line["Nom du type d’élément Français"] == "Inclusion(s)":
                    classified["inclusions"].append(newitem)
                if line["Nom du type d’élément Français"] == "Exclusion(s)":
                    classified["exclusions"].append(newitem)
                if line["Nom du type d’élément Français"] == "Fonctions principales":
                    classified["duties"].append(newitem)
                if line["Nom du type d’élément Français"] == "Conditions d'accès à la profession":
                    classified["requirements"].append(newitem)
                if line["Nom du type d’élément Français"] == "Renseignements supplémentaires":
                    classified["other"].append(newitem)

                newitem = copy.deepcopy(newitem)
                newitem["type_french"] = line[
                    "Nom du type d’élément Français"].strip()
                allitems.append(newitem)

            for ke, va in classified.items():
                diclist_to_csv(
                    va,
                    os.path.join(destination, "elements", f"{ke}_{lang}.csv"),
                    encoding)

        elif k == "cls_en":
            filename = "classes"
            for line in csvs[k]:
                newitem = {
                    "noc_code": line["Code - NOC 2021 V1.0"].strip(),
                    "name_english": line["Class title"].strip(),
                    "description_english": line["Class definition"].strip(),
                }
                allitems.append(newitem)

        elif k == "cls_fr":
            filename = "classes"
            lang = "fr"
            for line in csvs[k]:
                newitem = {
                    "noc_code": line["Code dela CNP 2021 v1.0"].strip(),
                    "name_french": line["Titres de classes"].strip(),
                    "description_french":
                    line["Définitions de la classe"].strip(),
                }
                allitems.append(newitem)

        diclist_to_csv(allitems,
                       os.path.join(destination, f"{filename}_{lang}.csv"),
                       encoding)

    sources = [
        os.path.join(destination, "classes_en.csv"),
        os.path.join(destination, "classes_fr.csv")
    ]
    diclist_to_csv(
        combine_csvs_id(sources, 'noc_code')[0],
        os.path.join(destination, "classes.csv"), encoding)

    diclist_to_csv(
        combine_csvs_translate(
            os.path.join(destination, "elements_en.csv"),
            os.path.join(destination, "elements_fr.csv"),
            'name_english', 'name_french', 'noc_code'
        )[0],
        os.path.join(destination, "elements.csv"), encoding)


def loopfind(needle, haystack, key_match):
    for i in range(len(haystack)):
        if (haystack[i] == needle):
            return i, 1
    high_p = 0
    high_i = 0
    for i in range(len(haystack)):
        ifval = True
        for k, v in needle.items():
            if k != key_match:
                ifval = ifval and haystack[i][k] == v
                if not ifval:
                    break
        if not ifval:
            continue
        p = SequenceMatcher(None, haystack[i][key_match],
                            needle[key_match]).ratio()
        if p > high_p:
            high_p = p
            high_i = i
        if " " in needle[key_match]:
            reverse_string = " ".join(list(reversed(needle[key_match].split())))
            p = SequenceMatcher(None, haystack[i][key_match], reverse_string).ratio()
            if p > high_p:
                high_p = p
                high_i = i

    if high_p != 0:
        return high_i, high_p
    return False, False
