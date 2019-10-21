import sys
import os.path
import pprint
import re

import config
from scanner import CurriculumScanner
from PIL import Image, ImageDraw
from word_tools import WordGrouper


sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))


# REGEX
TABLE_OF_CONTENTS = re.compile('(?:table\bof\b)?contents', re.IGNORECASE)
PART = re.compile('^part(?:$|\b|)', re.IGNORECASE)
CHAPTER = re.compile('^chap(?:$|\.|ter)', re.IGNORECASE)
SECTION = re.compile('^sect(?:$|\.|ion)', re.IGNORECASE)

GROUP_IGNORE = re.compile(r'^[\s\.\-]+$')
# GROUP_IGNORE = None


class ContentsItem(object):
    def __init__(self, search_result, number=None):
        self.search_result = search_result
        self.number = number

        self.title = None
        self.description = None
        self.children = []

    def __str__(self):
        return '{} {}: {}'.format(self.__class__.__name__, self.number, self.title or '')

    @property
    def page(self):
        return self.search_result.get('page')

    @property
    def block(self):
        return self.search_result.get('block')

    @property
    def paragraph(self):
        return self.search_result.get('paragraph')

    @property
    def min_y(self):
        return min(*[coordinate.get('y') for coordinate in self.search_result.get('bounds')])

    @property
    def max_y(self):
        return max(*[coordinate.get('y') for coordinate in self.search_result.get('bounds')])

    def add(self, content_item):
        if not content_item.number:
            content_item.number = len(self.children) + 1

        self.children.append(content_item)
        return self

    def is_before(self, contents_item):
        if self.page != contents_item.page:
            return self.page < contents_item.page

        if self.block != contents_item.block:
            return self.block < contents_item.block

        if self.paragraph != contents_item.paragraph:
            return self.paragraph < contents_item.paragraph

        if self.min_y != contents_item.min_y:
            return self.min_y < contents_item.min_y

        # Same level
        return None

    def find_parent_for(self, descendant_item, parent_type):
        for index, child in enumerate(self.children):
            if descendant_item.is_before(child):
                parent = self.children[index-1] if index > 0 else None
                break
        else:
            parent = self.children[-1] if self.children else None

        if parent is None:
            raise RuntimeError('Could not find item within children')

        if isinstance(parent, parent_type):
            return parent

        return parent.find_parent_for(descendant_item, parent_type)

    def flatten(self):
        flattened = [self]
        for child in self.children:
            flattened.extend(child.flatten())
        return flattened


class TableOfContents(ContentsItem):
    pass


class Part(ContentsItem):
    pass


class Chapter(ContentsItem):
    pass


class Section(ContentsItem):
    pass


class ContentItemSpan(object):
    def __init__(self, start_item, end_item):
        self.start = start_item
        self.end = end_item
        self.text = None

    def y_bounds(self):
        if not self.end or self.start.page != self.end.page:
            return self.start.max_y, None

        return self.start.max_y, self.end.min_y


class VerticalContentsHelper(object):
    def __init__(self, path):
        self.scanner = CurriculumScanner(path)
        self.contents = None

    def run(self):
        # Look for "Table of Contents" (TOC) starting point
        results = self.scanner.find_regex_matches(TABLE_OF_CONTENTS)

        if not results:
            raise ValueError('Could not find TOC starting point')

        # Use first match as starting point for TOC
        self.contents = TableOfContents(results[0])
        self.build_parts()
        self.build_chapters()
        self.build_sections()

        items = self.contents.flatten()
        spans = [
            ContentItemSpan(start_item, end_item)
            for start_item, end_item in zip(items[:-1], items[1:])
        ]

        # add end
        spans.append(ContentItemSpan(items[-1], None))

        for page_num in range(len(self.scanner.pages)):
            if page_num < self.contents.page:
                continue

            page = self.scanner.get_page_data(page_num).get('pages')[0]
            for span in spans:
                if span.start.page != page_num:
                    continue
                y0, y1 = span.y_bounds()
                words = self.scanner.words_within(page_num, y0=y0, y1=y1)

                if not words:
                    continue

                word_grouper = WordGrouper(page['width'], page['height'], words,
                                           ignore_regex=GROUP_IGNORE)
                word_groups = word_grouper.group()

                for index, group in enumerate(word_groups):
                    print('Group {}'.format(index))
                    print('\t{}'.format(group.text))


    def build_parts(self):
        part_results = self.scanner.find_regex_matches(PART)

        for part_result in part_results:
            part = Part(part_result)

            if part.is_before(self.contents):
                continue

            self.contents.add(part)

    def build_chapters(self):
        chapter_results = self.scanner.find_regex_matches(CHAPTER)

        for chapter_result in chapter_results:
            chapter = Chapter(chapter_result)

            if chapter.is_before(self.contents):
                continue

            part = self.contents.find_parent_for(chapter, Part)
            part.add(chapter)

    def build_sections(self):
        section_results = self.scanner.find_regex_matches(SECTION)

        for section_result in section_results:
            section = Section(section_result)

            if section.is_before(self.contents):
                continue

            chapter = self.contents.find_parent_for(section, Chapter)
            chapter.add(section)



if __name__ == '__main__':

    # Make sure file path is provided
    # if not len(sys.argv) > 2:
    #   raise RuntimeError('Usage: examples/search_text.py <filepath> <search text>')

    # Process args
    # path = sys.argv[1]
    # text = sys.argv[2]
    path = "inputs/Chemistry textbook TOC C.pdf"

    helper = VerticalContentsHelper(path)
    helper.run()
    print(helper.contents)
    # pprint.pprint(helper.contents)
