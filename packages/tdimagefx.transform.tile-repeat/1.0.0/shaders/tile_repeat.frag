uniform float uMix;
uniform vec2 uTiles;
uniform vec2 uOffset;
uniform float uRotation;
uniform float uMirror;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float c = cos(uRotation);
    float s = sin(uRotation);
    vec2 field = mat2(c, -s, s, c) * (uv - 0.5) + 0.5 + uOffset;
    vec2 tiled = field * max(abs(uTiles), vec2(0.0001));
    vec2 local = fract(tiled);
    vec2 mirrored = 1.0 - abs(fract(tiled * 0.5) * 2.0 - 1.0);
    local = mix(local, mirrored, step(0.5, uMirror));
    vec4 repeated = texture(sTD2DInputs[0], local);
    fragColor = TDOutputSwizzle(mix(source, repeated, clamp(uMix, 0.0, 1.0)));
}
