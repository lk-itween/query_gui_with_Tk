from functools import wraps
from threading import Thread
from sqlalchemy import create_engine, inspect, MetaData, and_
from sqlalchemy.orm import sessionmaker
import pandas as pd


class MyThread(Thread):
    """
    重写Thread.run方法
    """

    def __init__(self, target=None, args=(), kwargs=None):
        super(MyThread, self).__init__()
        self.func = target
        self.args = args
        self.kwargs = kwargs
        self.result = None

    def run(self):
        """覆盖父类的run方法"""
        try:
            self.result = self.func(*self.args, **self.kwargs)
        except:
            Exception('线程处理错误')


def threader_run(func):
    """线程装饰器"""

    @wraps(func)
    def thread(*args, **kwargs):
        t = MyThread(target=func, args=args, kwargs=kwargs)
        t.start()
        t.join()
        return t.result

    return thread


class MysqlCON:

    def __init__(self, ip, port, root, pwd):
        super().__init__()
        self.root = root
        self.pwd = pwd
        self.ip = ip
        self.port = port
        self.session = sessionmaker()()
        self.metadata = MetaData()
        self.table_dict = {}
        self.cols = []
        self.save_flag = 0
        self.mysql_dburl = f'mysql+mysqlconnector://{root}:{pwd}@{ip}:{port}'

    def connect_mysql(self):
        """连接数据库，返回数据库下的各个库名"""
        mysql_db = create_engine(self.mysql_dburl, pool_recycle=7200)
        try:
            # 通过映射关系，返回数据库结构
            insp = inspect(mysql_db)
        except Exception as e:
            return str(e)
        self.session = sessionmaker(mysql_db)()
        self.metadata = MetaData(mysql_db)
        return insp.get_schema_names()

    def get_tables(self, schema):
        """传入数据库名，返回该数据库下的所有数据表名"""
        if not self.metadata.is_bound():
            return
        self.metadata.clear()
        self.metadata.reflect(schema=schema)
        self.table_dict = {i.name: i for i in self.metadata.tables.values()}
        return list(self.table_dict.keys())

    @threader_run
    def get_table_all_data(self, table_name):
        """获取表的所有数据"""
        if not table_name:
            return
        self.session.commit()
        table = self.table_dict.get(table_name)
        self.cols = table.columns.keys()
        return pd.DataFrame(self.session.query(table).all(), columns=self.cols)

    @threader_run
    def query_exec(self, db_name, sql_str):
        """
        根据原生SQL获取数据
        :param db_name: 数据库名称
        :param sql_str: 原生sql
        :return: pandas.DataFrame
        """
        uri = f'{self.mysql_dburl}/{db_name}'
        engine = create_engine(uri, pool_recycle=7200)
        with engine.connect() as conn:
            try:
                result = conn.execute(sql_str)
                self.cols = [i[0] for i in result.cursor.description]
                result = result.fetchall()
                return pd.DataFrame(result, columns=self.cols)
            except Exception as e:
                return str(e)

    @threader_run
    def save_database(self, db_name, table_name, data):
        """保存数据至数据库"""
        self.save_flag = 0
        uri = f'{self.mysql_dburl}/{db_name}'
        engine = create_engine(uri, pool_recycle=7200)
        session = sessionmaker(engine)()
        data.to_sql(table_name, con=engine, index=False, if_exists='append', chunksize=1000)
        session.commit()
        self.save_flag = 1
        return

    @threader_run
    def delete_data(self, table_name, key, data):
        """从数据库删除指定数据"""
        self.session.commit()
        table = self.table_dict.get(table_name)
        query = self.session.query(table)
        data.columns = [table.columns.get(i) for i in data.columns]
        try:
            if key:
                key = table.columns.get(key)
                data = data[key]
                query.filter(key.in_(data.values.tolist())).delete()
            else:
                data.apply(
                    lambda row: query.filter(and_(*(map(lambda x, y: x == y, row.index, row.values)))).delete(), axis=1)
            self.session.commit()
        except Exception as e:
            self.session.rollback()

    @threader_run
    def modify(self, table_name, data):
        """修改数据"""
        self.session.commit()
        table = self.table_dict.get(table_name)
        query = self.session.query(table)
        data.columns = [table.columns.get(i) for i in data.columns]
        try:
            data.apply(
                lambda row: query.filter(and_(*(map(lambda x, y: x == y,
                                                    row.index, row.values)))).update(row.to_dict()), axis=1)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
