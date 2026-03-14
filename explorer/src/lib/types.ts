export type Parameter = {
  name: string;
  type: string;
  required: boolean;
  default: any;
  schema: Schema | null;
};

export type Schema =
  | { kind: 'enum'; values: string[] }
  | { kind: 'object'; fields: ObjectField[] };

export type ObjectField = {
  name: string;
  type: string;
  required: boolean;
  default: any;
  schema: Schema | null;
};

export type FunctionMeta = {
  key: string;
  name: string;
  module: string;
  file_path: string | null;
  route: string;
  decorator_type: 'query' | 'command' | 'form' | 'prerender' | 'query_batch';
  docstring: string | null;
  return_type: string;
  parameters: Parameter[];
};

export type GroupBy = 'file' | 'decorator';
