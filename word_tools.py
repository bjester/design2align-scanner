import re
from scanner import BREAK_MAP

ALIGNMENT_LEFT = 'left'
ALIGNMENT_CENTER = 'center'
ALIGNMENT_RIGHT = 'right'


def list_min(values):
    if not isinstance(values, (list, tuple)):
        return values

    if len(values) <= 1:
        return None if len(values) == 0 else values[0]

    return min(*values)


def list_max(values):
    if not isinstance(values, (list, tuple)):
        return values

    if len(values) <= 1:
        return None if len(values) == 0 else values[0]

    return max(*values)


def slope(point_a, point_b):
    if point_a == point_b:
        return 0
    return (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])


class Element(object):
    @property
    def bounds(self):
        raise NotImplementedError('Bounds property must be implemented')

    @property
    def text(self):
        raise NotImplementedError('Text property must be implemented')

    @property
    def break_text(self):
        raise NotImplementedError('Break text property must be implemented')

    @property
    def x_coordinates(self):
        return self.coordinates('x')

    @property
    def y_coordinates(self):
        return self.coordinates('y')

    @property
    def min_y(self):
        return sum(self.y_coordinates[:2]) / 2

    @property
    def max_y(self):
        return sum(self.y_coordinates[2:]) / 2

    @property
    def min_x(self):
        return sum(self.x_coordinates[:2]) / 2

    @property
    def max_x(self):
        return sum(self.x_coordinates[2:]) / 2

    @property
    def center_x(self):
        return self.min_x + (self.width / 2)

    @property
    def center_y(self):
        return self.min_y + (self.height / 2)

    @property
    def center(self):
        return self.center_x, self.center_y

    @property
    def height(self):
        return abs(self.max_y - self.min_y)

    @property
    def width(self):
        return abs(self.max_x - self.min_x)

    @property
    def left_midpoint(self):
        return self.min_x, self.center_y

    @property
    def right_midpoint(self):
        return self.max_x, self.center_y

    @property
    def slope(self):
        lower = self.y_coordinates[:2]
        upper = self.y_coordinates[2:]
        width = self.width

        lower_slope = (lower[1] - lower[0]) / width
        upper_slope = (upper[1] - upper[0]) / width

        return (lower_slope + upper_slope) / 2

    def coordinates(self, axis):
        return sorted([vertex.get(axis) for vertex in self.bounds])


class GroupedElement(Element):
    def __init__(self):
        self.children = []
        self._bounds = None

    def add(self, child):
        self.reset_bounds()
        self.children.append(child)
        return self

    def is_empty(self):
        return len(self) == 0

    def reset_bounds(self):
        self._bounds = None
        return self

    def __len__(self):
        return len(self.children)

    @property
    def bounds(self):
        if self._bounds is None:
            min_x = list_min([child.min_x for child in self.children])
            max_x = list_max([child.max_x for child in self.children])
            min_y = list_min([child.min_y for child in self.children])
            max_y = list_max([child.max_y for child in self.children])

            self._bounds = [
                {'x': min_x, 'y': min_y},
                {'x': min_x, 'y': max_y},
                {'x': max_x, 'y': max_y},
                {'x': max_x, 'y': min_y},
            ]
        return self._bounds

    @property
    def text(self):
        text = ''
        for child in self.children:
            text += child.text + child.break_text

        return text

    @property
    def break_text(self):
        return '\n'

    @property
    def slope(self):
        if len(self) == 0:
            return 0

        if len(self) == 1:
            return self.children[0].slope

        slopes = [
            slope(child_a.center, child_b.center)
            for child_a, child_b in zip(self.children[:-1], self.children[1:])
        ]

        if len(slopes) == 1:
            return slopes[0]

        return sum(slopes) / (len(self) - 1)


class Word(Element):
    def __init__(self, element):
        self.element = element

    @property
    def bounds(self):
        return self.element.get('bounding_box').get('vertices')

    @property
    def text(self):
        return self.element['text']

    @property
    def break_text(self):
        return BREAK_MAP.get(self.element['property']['detected_break']['type']) or ''


class Line(GroupedElement):
    def __init__(self):
        super(Line, self).__init__()
        self.alignment = None


class LineGroup(GroupedElement):
    pass


DEFAULT_PROXIMITY_THRESHOLDS = {
    'word': 35,
    'line': 12,
    'line_slope': 1,
    'group': 7,
    'height': 10,
}


class WordGrouper(object):
    """
    This will only work for LTR docs
    """
    def __init__(self, page_width, page_height, words, ignore_regex=None, proximity_thresholds=None):
        self.page_width = page_width
        self.page_height = page_height
        self.words = [Word(word) for word in words]

        self.ignore_regex = ignore_regex
        self.proximity_thresholds = DEFAULT_PROXIMITY_THRESHOLDS.copy()
        self.proximity_thresholds.update(**(proximity_thresholds or {}))

        first_group = LineGroup()
        first_line = Line()
        first_line.add(self.words.pop(0))
        first_group.add(first_line)
        self.line_groups = [first_group]

    def group(self):
        for word in self.words:
            group = self.line_groups[-1]
            last_line = group.children[-1]

            if self.word_in_line(word, last_line):
                last_line.add(word)
                continue

            new_line = Line()
            new_line.add(word)

            if self.line_in_group(new_line, group):
                group.add(new_line)
                continue

            new_group = LineGroup()
            new_group.add(new_line)
            self.line_groups.append(new_group)

        self.clean_words()
        # while self.clean_groups():
        #     pass

        return self.line_groups

    def clean_words(self):
        groups_to_remove = []

        for group in self.line_groups:
            lines_to_remove = []

            for line in group.children:
                if line.is_empty():
                    lines_to_remove.append(line)
                    continue

                self.trim_line(line)
                matched = False
                words_to_remove = []

                for word in line.children:
                    if re.fullmatch(self.ignore_regex, word.text) is not None:
                        if matched:
                            words_to_remove.append(word)
                        matched = True
                    else:
                        matched = False

                for word in words_to_remove:
                    line.children.remove(word)

                if line.is_empty():
                    lines_to_remove.append(line)
                line.reset_bounds()

            for line in lines_to_remove:
                group.children.remove(line)
            group.reset_bounds()

            if group.is_empty():
                groups_to_remove.append(group)

        for group in groups_to_remove:
            self.line_groups.remove(group)

    def trim_line(self, line):
        if line.is_empty():
            return

        line.children.reverse()
        line.children = self.do_trim_line_words(line.children)

        if not line.is_empty():
            line.children.reverse()
            line.children = self.do_trim_line_words(line.children)

        line.reset_bounds()

    def do_trim_line_words(self, words):
        while len(words):
            word = words.pop(-1)
            if re.fullmatch(self.ignore_regex, word.text) is None:
                words.append(word)
                break
        return words

    def clean_groups(self):
        if not self.ignore_regex:
            return False

        for group_index, group in enumerate(self.line_groups):
            for line_index, line in enumerate(group.children):
                for word_index, word in enumerate(line.children):
                    if re.fullmatch(self.ignore_regex, word.text) is None:
                        break
                else:
                    if group_index == 0:
                        self.line_groups.pop(0)
                        return True
                    if (group_index + 1) >= len(self.line_groups):
                        self.line_groups.pop(group_index)
                        # Return False as no more groups to process
                        return False

                    previous_group = self.line_groups[group_index-1]
                    previous_line = previous_group.children[-1]
                    next_group = self.line_groups[group_index+1]
                    next_line = next_group.children[0]

                    if self.is_in_line(previous_line, next_line):
                        next_group.children.remove(next_line)
                        previous_line.children.extend(next_line.children)
                        previous_group.children.extend(next_group.children)

                        previous_line.reset_bounds()
                        previous_group.reset_bounds()
                        self.line_groups.remove(next_group)
                        self.line_groups.remove(group)
                        return True
                break
            group.reset_bounds()

        return False

    def is_in_line(self, element, line):
        if slope(line.center, element.center) > self.proximity_thresholds['line_slope']:
            return False

        # slope_adjustment = abs(element.min_x - line.max_x) * line.slope

        # if abs(element.center_y - line.center_y + slope_adjustment) > self.proximity_thresholds['line']:
        #     return False

        if abs(element.height - line.height) > self.proximity_thresholds['height']:
            return False

        return True

    def word_in_line(self, word, line):
        return self.is_in_line(word, line) \
               and abs(word.min_x - line.max_x) < self.proximity_thresholds['word']

    def line_in_group(self, line, group):
        # last_group_line = group.children[-1]
        #
        # if abs(line.center_y - last_group_line.center_y) <= self.proximity_thresholds['line']\
        #         and abs(line.min_x - group.max_x) > self.proximity_thresholds['word']:
        #     return False

        # if abs(line.height - group.height) > self.proximity_thresholds['height']:
        #     return False

        if abs(line.min_y - group.max_y) > self.proximity_thresholds['group']:
            return False

        return True
