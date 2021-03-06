# Copyright (C) 2014-2016 Oleh Prypin <blaxpirit@gmail.com>
# 
# This file is part of SixCells.
# 
# SixCells is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# SixCells is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with SixCells.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import division, print_function

__version__ = '2.4.3'

import sys
import os.path
import math
import collections
import itertools
import contextlib

from util import *

from universal_qt import PySide, PyQt4, PyQt5
import qt
from qt.core import QByteArray, QEvent, QPointF, QRect, QUrl
from qt.gui import QBrush, QColor, QCursor, QDesktopServices, QMouseEvent, QPainter, QPen, QPolygonF
from qt.widgets import QAction, QActionGroup, QApplication, QFileDialog, QGraphicsPolygonItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QMainWindow, QMessageBox, QGraphicsItem

from config import *

app = QApplication(sys.argv)



tau = 2*math.pi # 360 degrees is better than 180 degrees
cos30 = math.cos(tau/12)

class Color(object):
    background = QColor(231, 231, 231)
    yellow = QColor(255, 175, 41)
    yellow_border = QColor(255, 159, 0)
    blue = QColor(5, 164, 235)
    blue_border = QColor(20, 156, 216)
    black = QColor(62, 62, 62)
    black_border = QColor(44, 47, 49)
    light_text = QColor(255, 255, 255)
    dark_text = QColor(73, 73, 73)
    border = qt.white
    beam = QColor(255, 255, 255, 110)
    flower = QColor(255, 255, 255, 90)
    flower_border = QColor(128, 128, 128, 192)
    revealed_border = QColor(0, 230, 80)
    selection = qt.black


no_pen = QPen(qt.transparent, 1e-10, qt.NoPen)


def fit_inside(parent, item, k):
    "Fit one QGraphicsItem inside another, scale by height and center it"
    sb = parent.boundingRect()
    tb = item.boundingRect()
    item.setScale(sb.height()/tb.height()*k)
    tb = item.mapRectToItem(parent, item.boundingRect())
    item.setPos(sb.center() - QPointF(tb.size().width()/2, tb.size().height()/2))

def update_font(obj, f):
    font = obj.font()
    r = f(font)
    if r: font = r
    obj.setFont(font)

def multiply_font_size(font, k):
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF()*k)
    else:
        font.setPixelSize(round(font.pixelSize()*k))


def make_check_action(text, obj, *args):
    action = QAction(text, obj)
    action.setCheckable(True)
    if args:
        if len(args) == 1:
            args = (obj,) + args
        def set_attribute(value):
            setattr(*(args + (value,)))
        action.toggled.connect(set_attribute)
    return action

def make_action_group(parent, menu, obj, attribute, items):
    group = QActionGroup(parent)
    group.setExclusive(True)
    result = collections.OrderedDict()
    for it in items:
        try:
            text, value = it
            tip = None
        except ValueError:
            text, value, tip = it
        action = make_check_action(text, parent)
        if tip:
            action.setStatusTip(tip)
        group.addAction(action)
        menu.addAction(action)
        def set_attribute(truth, value=value):
            if truth:
                setattr(obj, attribute, value)
        action.toggled.connect(set_attribute)
        result[value] = action
    return result



def hex1():
    result = QPolygonF()
    l = 0.5/cos30
    for i in range(6):
        a = i*tau/6 - tau/12
        result.append(QPointF(l*math.sin(a), -l*math.cos(a)))
    return result
hex1 = hex1()

class Item(object):
    placed = False
    
    def _remove_from_grid(self):
        try:
            if self.scene().grid[tuple(self.coord)] is self:
                del self.scene().grid[tuple(self.coord)]
        except (AttributeError, KeyError):
            pass
    
    @setter_property
    def coord(self, value):
        x, y = value
        yield Point(x, y)
        self.setPos(x*cos30, y/2)
    
    def place(self, coord=None):
        self._remove_from_grid()
        if coord is not None:
            self.coord = coord
        self.scene().grid[self.coord.x, self.coord.y] = self
        try:
            del self.scene().grid_bounds
        except AttributeError:
            pass
        self.placed = True
    
    def remove(self):
        self._remove_from_grid()
        if self.scene():
            self.scene().removeItem(self)
        self.placed = False
    
    def _find_neighbors(self, deltas, cls):
        try:
            x, y = self.coord
        except AttributeError:
            return
        for dx, dy in deltas:
            it = self.scene().grid.get((x + dx, y + dy))
            if isinstance(it, cls):
                yield it

    @property
    def overlapping(self):
        return list(self._find_neighbors(_colliding_deltas, (Cell, Column)))


def _cell_polys():
    poly = QPolygonF()
    l = 0.46/cos30
    inner_poly = QPolygonF()
    il = 0.75*l
    for i in range(6):
        a = i*tau/6 - tau/12
        poly.append(QPointF(l*math.sin(a), -l*math.cos(a)))
        inner_poly.append(QPointF(il*math.sin(a), -il*math.cos(a)))
    return poly, inner_poly
_cell_outer, _cell_inner = _cell_polys()

_flower_deltas = [ # order: (clockwise, closest) starting from north
    ( 0, -2), ( 0, -4), ( 1, -3),
    ( 1, -1), ( 2, -2), ( 2,  0),
    ( 1,  1), ( 2,  2), ( 1,  3),
    ( 0,  2), ( 0,  4), (-1,  3),
    (-1,  1), (-2,  2), (-2,  0),
    (-1, -1), (-2, -2), (-1, -3),
]
_neighbors_deltas = _flower_deltas[::3] # order: clockwise starting from north
_columns_deltas = _neighbors_deltas[-1], _neighbors_deltas[0], _neighbors_deltas[1]
_colliding_deltas = [(0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)]

class Cell(QGraphicsPolygonItem, Item):
    "Hexagonal cell"
    unknown = Entity('Cell.unknown')
    empty = Entity('Cell.empty')
    full = Entity('Cell.full')
    
    def __init__(self):
        QGraphicsPolygonItem.__init__(self, _cell_outer)
        
        self._inner = QGraphicsPolygonItem(_cell_inner)
        self._inner.setPen(no_pen)

        pen = QPen(Color.border, 0.03)
        pen.setJoinStyle(qt.MiterJoin)
        self.setPen(pen)

        self._text = QGraphicsSimpleTextItem('{?}')
        self._text.setBrush(Color.light_text)
        update_font(self._text, lambda f: f.setWeight(55))
        
        self._extra_text = QGraphicsSimpleTextItem('')
        
        self.kind = Cell.unknown
        self.show_info = 0

    @property
    def display(self):
        return self.kind
    
    @cached_property
    def neighbors(self):
        return list(self._find_neighbors(_neighbors_deltas, Cell))
    @cached_property
    def flower_neighbors(self):
        return list(self._find_neighbors(_flower_deltas, Cell))
    @cached_property
    def columns(self):
        result = []
        for col in self._find_neighbors(_columns_deltas, Column):
            sgn = col.angle//60
            if sgn == col.coord.x-self.coord.x:
                result.append(col)
        return result
    
    @cached_property
    def members(self):
        if self.show_info:
            if self.kind is Cell.empty:
                return self.neighbors
            if self.kind is Cell.full:
                return self.flower_neighbors

    def is_neighbor(self, other):
        return other in self.neighbors

    @cached_property
    def value(self):
        if self.show_info:
            return sum(1 for it in self.members if it.kind is Cell.full)
    
    @cached_property
    def together(self):
        if self.show_info == 2:
            full_items = {it for it in self.members if it.kind is Cell.full}
            return all_grouped(full_items, key=Cell.is_neighbor)

    def reset_cache(self):
        for attr in ['neighbors', 'flower_neighbors', 'columns', 'members', 'value', 'together']:
            try:
                delattr(self, attr)
            except AttributeError: pass
    
    @property
    def extra_text(self):
        return self._extra_text.text().replace('\n', '')
    @extra_text.setter
    def extra_text(self, value):
        value = value[:3]
        self._extra_text.setText(value)
        self.upd()
    
    def keyPressEvent(self, e):
        for c in e.text():
            c = c.upper()
            if c.isdigit() or e.modifiers() & (qt.ShiftModifier):
                if c not in ['Q', 'W']:
                    self.extra_text += c
        if e.key() in [qt.Key_Backspace, qt.Key_QuoteLeft, qt.Key_AsciiTilde] or\
          e.text() in [u'`', u'~', u'^', u'\\', u'\N{SECTION SIGN}']:
            if not (e.modifiers() & qt.ShiftModifier):
                self.guess = None
                self.extra_text = ''
    
    def upd(self, first=False):
        self.reset_cache()
        
        if self.display is Cell.unknown:
            self.setBrush(Color.yellow_border)
            self._inner.setBrush(Color.yellow)
            self._text.setText('')
        elif self.display is Cell.empty:
            self.setBrush(Color.black_border)
            self._inner.setBrush(Color.black)
        elif self.display is Cell.full:
            self.setBrush(Color.blue_border)
            self._inner.setBrush(Color.blue)
        
        if not self.placed:
            return
        
        if self.display is not Cell.unknown and self.value is not None:
            txt = str(self.value)
            if self.together is not None:
                txt = ('{{{}}}' if self.together else '-{}-').format(txt)
        else:
            txt = '?' if self.display is Cell.empty else ''
        
        self._text.setText(txt)
        if txt:
            fit_inside(self, self._text, 0.48)
        
        if self.extra_text:
            unknown = self.display is Cell.unknown
            fit_inside(self, self._extra_text, 0.31)
            self._extra_text.setPos(self._extra_text.pos() + QPointF(0, -0.2))
            self._extra_text.setBrush(Color.dark_text if unknown else Color.light_text)
        
        if txt and self.extra_text:
            self._text.setPos(self._text.pos() + QPointF(0, 0.1))

        self.update()
        
        if first:
            with self.upd_neighbors():
                pass
    
    @contextlib.contextmanager
    def upd_neighbors(self):
        neighbors = list(self.flower_neighbors)
        scene = self.scene()
        yield
        for it in neighbors:
            it.upd()
        for it in scene.all(Column):
            it.upd()
    
    def paint(self, g, option, widget):
        QGraphicsPolygonItem.paint(self, g, option, widget)
        self._inner.paint(g, option, widget)
        transform = g.transform()
        g.setTransform(self._extra_text.sceneTransform(), True)
        self._extra_text.paint(g, option, widget)
        g.setTransform(transform)
        g.setTransform(self._text.sceneTransform(), True)
        g.setOpacity(self._text.opacity())
        self._text.paint(g, option, widget)
    
    def __repr__(self, first=True):
        r = [self.display]
        if self.display!=self.kind:
            r.append('({})'.format(repr(self.kind).split('.')[1]))
        r.append(self._text.text())
        try:
            r.append('#{}'.format(self.id))
        except AttributeError: pass
        if first:
            r.append('neighbors:[{}]'.format(' '.join(m.__repr__(False) for m in self.neighbors)))
            if self.members:
                r.append('members:[{}]'.format(' '.join(m.__repr__(False) for m in self.members)))
        return '<{}>'.format(' '.join(str(p) for p in r if str(p)))


_col_poly = QPolygonF()
for x, y in [(-0.25, 0.48), (-0.25, 0.02), (0.25, 0.02), (0.25, 0.48)]:
    _col_poly.append(QPointF(x, y))

_col_angle_deltas = {-60: (1, 1), 0: (0, 1), 60: (-1, 1)}

class Column(QGraphicsPolygonItem, Item):
    "Column number marker"
    def __init__(self):
        QGraphicsPolygonItem.__init__(self, _col_poly)

        self.show_info = False

        self.setBrush(QColor(255, 255, 255, 0))
        self.setPen(no_pen)
        
        self._text = QGraphicsSimpleTextItem('v')
        self._text.setBrush(Color.dark_text)
        update_font(self._text, lambda f: f.setWeight(55))
        fit_inside(self, self._text, 0.86)
        #self._text.setY(self._text.y()+0.2)
    
    @setter_property
    def angle(self, value):
        if value not in (-60, 0, 60):
            raise ValueError(value)
        yield value
    
    @property
    def cell(self):
        return self.members[0]

    @cached_property
    def members(self):
        try:
            x, y = self.coord
        except AttributeError:
            return
        result = []
        dx, dy = _col_angle_deltas[self.angle]
        while True:
            x += dx
            y += dy
            it = self.scene().grid.get((x, y))
            if not it and not self.scene().grid_bounds.contains(x, y, False):
                break
            if isinstance(it, Cell):
                result.append(it)
        return result

    @cached_property
    def value(self):
        return sum(1 for it in self.members if it.kind is Cell.full)

    @cached_property
    def together(self):
        if self.show_info:
            groups = itertools.groupby(self.members, key=lambda it: it.kind is Cell.full)
            return sum(1 for full, _ in groups if full) <= 1

    def reset_cache(self):
        for attr in ['members', 'value', 'together']:
            try:
                delattr(self, attr)
            except AttributeError: pass

    def upd(self):
        self.reset_cache()
        
        self.setRotation(self.angle or 1e-3) # not zero so font doesn't look different from rotated variants
        
        if not self.placed:
            return
        
        txt = str(self.value)
        together = self.together
        if together is not None:
            txt = ('{{{}}}' if together else '-{}-').format(txt)
        self._text.setText(txt)
        if txt:
            self._text.setX(-self._text.boundingRect().width()*self._text.scale()/2)
        
        self.update()

    def paint(self, g, option, widget):
        QGraphicsPolygonItem.paint(self, g, option, widget)
        g.setTransform(self._text.sceneTransform(), True)
        self._text.paint(g, option, widget)

    def __repr__(self):
        r = ['Column']
        r.append(self._text.text())
        try:
            r.append('#{}'.format(self.id))
        except AttributeError: pass
        r.append('members:[{}]'.format(' '.join(m.__repr__(False) for m in self.members)))
        return '<{}>'.format(' '.join(str(p) for p in r if str(p)))


class Scene(QGraphicsScene):
    def __init__(self):
        QGraphicsScene.__init__(self)
        self.grid = dict()
    
    def all(self, types=(Cell, Column)):
        return (it for it in self.grid.values() if isinstance(it, types))
    
    @cached_property
    def grid_bounds(self):
        #return QRect(-100, -100, 200, 200)
        it = iter(self.grid)
        try:
            minx, miny = next(it)
            maxx = minx
            maxy = miny
        except StopIteration:
            return QRect()
        for x, y in it:
            if   x < minx: minx = x
            elif x > maxx: maxx = x
            if   y < miny: miny = y
            elif y > maxy: maxy = y
        return QRect(minx, miny, maxx-minx+1, maxy-miny+1)

    def full_upd(self):
        for cell in self.all(Cell):
            cell.upd(False)
        for col in self.all(Column):
            col.upd()

    def clear(self):
        self.grid = dict()
        QGraphicsScene.clear(self)



class View(QGraphicsView):
    def __init__(self, scene):
        QGraphicsView.__init__(self, scene)
        self.scene = scene
        self.setBackgroundBrush(QBrush(Color.background))
        self.antialiasing = True
        self.setHorizontalScrollBarPolicy(qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(qt.ScrollBarAlwaysOff)
    
    @property
    def antialiasing(self):
        return bool(self.renderHints() & QPainter.Antialiasing)
    @antialiasing.setter
    def antialiasing(self, value):
        self.setRenderHint(QPainter.Antialiasing, value)
        self.setRenderHint(QPainter.TextAntialiasing, value)

    def _get_event(self, e, typ):
        if e.isAutoRepeat():
            return None
        try:
            btn = {
                qt.Key_Q: qt.LeftButton,
                qt.Key_W: qt.RightButton,
                qt.Key_E: qt.MiddleButton,
            }[e.key()]
        except KeyError:
            return None
        pos = self.mapFromGlobal(QCursor.pos())
        return QMouseEvent(typ, pos, btn, btn, e.modifiers())
    
    def keyPressEvent(self, e):
        evt = self._get_event(e, QEvent.MouseButtonPress)
        if evt:
            self.mousePressEvent(evt)
        else:
            QGraphicsView.keyPressEvent(self, e)
        item = self.itemAt(self.mapFromGlobal(QCursor.pos()))
        if item:
            item.keyPressEvent(e)

    def keyReleaseEvent(self, e):
        evt = self._get_event(e, QEvent.MouseButtonRelease)
        if evt:
            self.mouseReleaseEvent(evt)
        else:
            QGraphicsView.keyReleaseEvent(self, e)


hexcells_ui_area = [
    '     *************************   ',
    '     *#######################*   ',
    '    *########################*   ',
    '    *########################*   ',
    '   *#########################*   ',
    '   ##########################*   ',
    '  *##########################****',
    ' *###############################',
    ' *###############################',
    '*################################',
    '*################################'
] + [
    '#'*33
]*22

def save(scene, display=False, padding=True):
    ret = None
    
    grid = scene.grid
    all_cells = [(x, y) for (x, y), it in grid.items() if isinstance(it, Cell)]
    min_x, max_x = minmax([x for x, y in grid] or [0])
    min_y, max_y = minmax([y for x, y in grid] or [0])
    if padding:
        mid_x, mid_y = (min_x + max_x)//2, (min_y + max_y)//2
        max_tx = max_ty = 32

        if max_x - min_x > max_tx:
            ret = "This level is too wide to fit into Hexcells format."
        if max_y - min_y > max_tx:
            ret = "This level is too high to fit into Hexcells format."
        if ret:
            ret += '\n' + "The data will be malformed, but still readable by SixCells."
            max_tx = max_x - min_x
            max_ty = max_y - min_y

        mid_t = (0 + max_tx)//2, (0 + max_ty)//2
        mid_d = mid_t[0] - mid_x, mid_t[1] - mid_y

        ui_area = list(hexcells_ui_area)
        d = len(scene.information.splitlines())*2 - 2
        if d > 0:
            ui_area[-d:] = [' '*33]*d

        possibilities = []
        for dy in range(-min_y, -min_y + max_ty - (max_y - min_y) + 1):
            for dx in range(-min_x, -min_x + max_tx - (max_x - min_x) + 1):
                overlaps = 0
                if not ret:
                    for (x, y), it in grid.items():
                        c = ui_area[y+dy][x+dx]
                        if isinstance(it, Cell):
                            overlaps += {'#': 0, '*': 0.9, ' ': 1}[c]
                        if isinstance(it, Column):
                            overlaps += {'#': 0, '*': 0.001, ' ': 0.85}[c]
                dist = (
                    sum(distance(mid_t, (x+dx, y+dy), squared=True) for x, y in all_cells)/(len(all_cells) or 1)+
                    distance(mid_d, (dx, dy), squared=True)/2
                )
                possibilities.append((overlaps, dist, (dy, dx)))
        assert possibilities
        overlaps, _, (dy, dx) = min(possibilities)
        global level_center
        level_center = (16-dx, 16-dy)
        if overlaps > 0.8:
            ret = "This level (barely) fits, but may overlap some UI elements of Hexcells."
    else:
        dx, dy = -min_x, -min_y
        max_tx, max_ty = max_x+dx, max_y+dy
    
    level = [[['.', '.'] for x in range(max_tx+1)] for y in range(max_ty+1)]
    for (x, y), it in grid.items():
        r = level[y+dy][x+dx]
        if isinstance(it, Column):
            r[0] = {-60: '\\', 0: '|', 60: '/'}[int(it.angle)]
        else:
            kind = it.display if display and it.display is not Cell.unknown else it.kind
            r[0] = 'x' if kind is Cell.full else 'o'
        if it.value is not None:
            if it.together is not None:
                r[1] = 'c' if it.together else 'n'
            else:
                r[1] = '+'
        if isinstance(it, Cell) and (it.revealed or (display and it.display is not Cell.unknown)):
            r[0] = r[0].upper()
    level = [''.join(''.join(part) for part in line) for line in level]
    
    headers = [
        'Hexcells level v1',
        scene.title,
        scene.author,
        ('\n' if '\n' not in scene.information else '') + scene.information,
    ]
    
    level = '\n'.join(headers + level)
    if padding:
        return level, ret
    else:
        return level

def load(level, scene, Cell=Cell, Column=Column):
    lines = iter(level.strip().splitlines())

    try:
        header = next(lines).strip()
        if header != 'Hexcells level v1':
            raise ValueError("Can read only Hexcells level v1")

        scene.title = next(lines).strip()
        scene.author = next(lines).strip()
        scene.information = '\n'.join(line for line in [next(lines).strip(), next(lines).strip()] if line)
    except StopIteration:
        raise ValueError("Level data stopped abruptly")

    for y, line in enumerate(lines):
        line = line.strip().replace(' ', '')
        
        row = []
        
        for x in range(0, len(line)//2):
            kind, value = line[x*2:x*2+2]
            
            if kind.lower() in 'ox':
                item = Cell()
            elif kind in '\\|/':
                item = Column()
            else:
                continue
            
            if isinstance(item, Cell):
                item.kind = Cell.full if kind.lower() == 'x' else Cell.empty
                item.revealed = kind.isupper()
                item.show_info = 0 if value == '.' else 1 if value == '+' else 2
            else:
                item.angle = (-60 if kind == '\\' else 60 if kind == '/' else 0)
                item.show_info = False if value == '+' else True
            
            scene.addItem(item)
            item.place((x, y))
        
    scene.full_upd()
    

class MainWindow(QMainWindow):
    def load(self, level):
        if not self.close_file():
            return
        self.status = "Loading a level..."
        try:
            load(level, self.scene, Cell=self.Cell, Column=self.Column)
        except ValueError as e:
            QMessageBox.critical(None, "Error", str(e))
            self.status = "Failed", 1
            return
        self.prepare()
        self.status = "Done", 1
        return True

    def load_file(self, fn=None):
        if not fn:
            try:
                dialog = QFileDialog.getOpenFileNameAndFilter
            except AttributeError:
                dialog = QFileDialog.getOpenFileName
            fn, _ = dialog(self, "Open", self.last_used_folder, "Hexcells Level (*.hexcells)")
        if not fn:
            return
        self.status = "Loading a level..."
        with open(fn, 'rb') as f:
            level = f.read().decode('utf-8')
        if self.load(level):
            if isinstance(fn, basestring):
                self.current_file = fn
                self.last_used_folder = os.path.dirname(fn)
            return True

    def paste(self):
        return self.load(app.clipboard().text())
    
    def copy(self, padded=True, **kwargs):
        self.status = "Copying to clipboard..."
        try:
            level, status = save(self.scene, **kwargs)
        except Exception as e:
            QMessageBox.critical(None, "Error", str(e))
            self.status = "Failed", 1
            return
        if status:
            QMessageBox.warning(None, "Warning", status + '\n' + "Copied anyway.")
        if padded:
            level = '\t' + level.replace('\n', '\n\t')
        app.clipboard().setText(level)
        self.status = "Done", 1
        return True

    def save_geometry_qt(self):
        return str(self.saveGeometry().toBase64().data().decode('ascii'))
    def restore_geometry_qt(self, value):
        self.restoreGeometry(QByteArray.fromBase64(value.encode('ascii')))
    
    def about(self):
        try:
            import pulp
        except ImportError:
            pulp_version = "(missing!)"
        else:
            pulp_version = pulp.VERSION
        try:
            import sqlite3
        except ImportError:
            sqlite_version = "(missing!)"
        else:
            sqlite_version = sqlite3.sqlite_version
        
        QMessageBox.information(None, "About", """
            <h1>{}</h1>
            <h3>Version {}</h3>

            <p>&copy; 2014-2016 Oleh Prypin &lt;<a href="mailto:blaxpirit@gmail.com">blaxpirit@gmail.com</a>&gt;<br/>
            &copy; 2014 Stefan Walzer &lt;<a href="mailto:sekti@gmx.net">sekti@gmx.net</a>&gt;</p>

            <p>License: <a href="http://www.gnu.org/licenses/gpl.txt">GNU General Public License Version 3</a></p>

            Using:
            <ul>
            <li>Python {}
            <li>Qt {}
            <li>{} {}
            <li>PuLP {}
            <li>SQLite {}
            </ul>
        """.format(
            self.title, __version__,
            sys.version.split(' ', 1)[0],
            qt.version_str,
            qt.module, qt.module_version_str,
            pulp_version,
            sqlite_version,
        ))

    def help(self):
        QDesktopServices.openUrl(QUrl('https://github.com/oprypin/sixcells/tree/v{}#readme'.format(__version__)))
