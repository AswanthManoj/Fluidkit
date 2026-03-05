import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter(),
		alias: { '$fluidkit': './src/lib/fluidkit' },
		experimental: { remoteFunctions: true }
	},
	compilerOptions: { experimental: { async: true } }
};

export default config;