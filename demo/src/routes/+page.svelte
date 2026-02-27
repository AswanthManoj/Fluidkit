<script>
	import { get_posts, like_post, add_post } from '$lib/demo.remote';
	import IntroComponent from '$lib/components/IntroComponent.svelte';
</script>

<IntroComponent />

<section class="demo">
	<h2>Try it out</h2>

	{#each await get_posts() as post}
		<div class="card">
			<div class="content">
				<h3>{post.title}</h3>
				<p>{post.content}</p>
			</div>
			<button class="like" onclick={async () => await like_post(post.id)}>👍 {post.likes}</button>
		</div>
	{/each}

	<form {...add_post}>
		<input {...add_post.fields.title.as('text')} placeholder="Title" />
		<input {...add_post.fields.content.as('text')} placeholder="Content" />
		<button>Add Post</button>
	</form>
</section>

<style>
	.demo {
		max-width: 480px;
		margin: 0 auto;
		padding: 1.5rem 1.5rem 4rem;
	}

	h2 {
		font-size: 0.75rem;
		color: #57534e;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		text-align: center;
		margin: 0 0 1rem;
	}

	.card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 0;
		border-bottom: 1px solid rgba(255,255,255,0.05);
    }

	.content h3 { margin: 0; font-size: 0.9rem; color: #e7e5e4; }
	.content p { margin: 0.2rem 0 0; font-size: 0.8rem; color: #78716c; }

	.like {
		margin-left: 1rem;
		background: transparent;
		font-size: 0.75rem;
	}

	form {
		display: flex;
		gap: 0.5rem;
		margin-top: 1.25rem;
		padding-top: 1.25rem;
		border-top: 1px solid rgba(255,255,255,0.05);
	}

	input, button {
		padding: 0.45rem 0.7rem;
		border-radius: 6px;
		font-size: 0.8rem;
		border: 1px solid rgba(255,255,255,0.07);
		background: rgba(255,255,255,0.03);
		color: #a8a29e;
	}

	input {
		flex: 1;
		color: #d6d3d1;
		outline: none;
	}

	input::placeholder { color: #44403c; }
	input:focus { border-color: rgba(255,255,255,0.18); }
	button:hover { background: rgba(255,255,255,0.1); color: #e7e5e4; }
</style>
